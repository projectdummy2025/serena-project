import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class ClaudeStreamParser:
    """
    Parser mandiri untuk mengolah aliran output JSON (stream-json) dari Claude Code CLI.
    Mengekstrak status aktivitas langsung, jejak eksekusi tools, dan hasil akhir.
    """

    def __init__(self):
        # Inisialisasi state penampung data eksekusi
        self.latest_activity: str = "Memulai eksekusi tugas..."
        self.executed_tools: List[str] = []
        self.final_result: str = ""
        self.error_messages: List[str] = []
        self.has_error: bool = False

    def process_line(self, raw_line: str) -> Optional[str]:
        """
        Memproses satu baris teks output dari Claude Code CLI.
        Mengembalikan teks status aktivitas jika ada perubahan aktivitas baru.
        """
        clean_line = raw_line.strip()
        if not clean_line or not clean_line.startswith("{"):
            return None

        try:
            event_data = json.loads(clean_line)
        except Exception:
            return None

        event_type = event_data.get("type")

        # 1. Tangani event assistant (teks narasi dan pemanggilan tool)
        if event_type == "assistant":
            return self._handle_assistant_event(event_data)

        # 2. Tangani event user (hasil eksekusi tool)
        if event_type == "user":
            self._handle_user_event(event_data)
            return None

        # 3. Tangani event hasil akhir (final result)
        if event_type == "result":
            self._handle_result_event(event_data)
            return None

        return None

    def _format_tool_narrative(self, tool_name: str) -> str:
        """Menghasilkan narasi manusiawi berdasarkan jenis tool yang dipanggil."""
        tool_lower = tool_name.lower()
        if "bash" in tool_lower:
            return "Claude Code sedang mengeksekusi perintah terminal proyek."
        if any(w in tool_lower for w in ("read", "view", "cat")):
            return "Claude Code sedang memeriksa konfigurasi dan berkas dependensi."
        if any(w in tool_lower for w in ("write", "edit", "create", "modify")):
            return "Claude Code sedang menyusun dan memodifikasi kode sumber."
        if any(w in tool_lower for w in ("grep", "glob", "search", "find", "ls")):
            return "Claude Code sedang menelusuri struktur direktori dan berkas."
        if "codegraph" in tool_lower:
            return "Claude Code sedang memetakan arsitektur kode via CodeGraph."
        return "Claude Code sedang memproses tugas teknis."

    def _handle_assistant_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Ekstrak aktivitas narasi atau pemanggilan tool dari pesan assistant."""
        message = event_data.get("message", {})
        content_list = message.get("content", [])
        activity_update = None

        for item in content_list:
            item_type = item.get("type")

            # Ekstrak pesan teks status
            if item_type == "text":
                text_content = item.get("text", "").strip()
                if text_content and len(text_content) < 150:
                    clean_text = text_content[:80]
                    self.latest_activity = f"Claude Code sedang menelaah struktur proyek.\n\nAktivitas Terkini : `{clean_text}`"
                    activity_update = self.latest_activity

            # Ekstrak pemanggilan tool (Bash, Read, CodeGraph, dsb.)
            elif item_type == "tool_use":
                tool_name = item.get("name", "Tool")
                tool_input = item.get("input", {})
                tool_summary = self._format_tool_summary(tool_name, tool_input)

                self.executed_tools.append(tool_summary)
                narrative = self._format_tool_narrative(tool_name)
                self.latest_activity = f"{narrative}\n\nAktivitas Terkini : `{tool_summary}`"
                activity_update = self.latest_activity

        return activity_update

    def _handle_user_event(self, event_data: Dict[str, Any]):
        """Evaluasi apakah ada error pada hasil eksekusi tool."""
        message = event_data.get("message", {})
        content_list = message.get("content", [])

        for item in content_list:
            if item.get("type") == "tool_result" and item.get("is_error"):
                self.has_error = True
                error_text = str(item.get("content", "Terjadi kegagalan pada eksekusi tool"))
                self.error_messages.append(error_text[:200])

    def _handle_result_event(self, event_data: Dict[str, Any]):
        """Ekstrak hasil akhir dan status terminal dari event result."""
        result_text = event_data.get("result", "")
        if result_text:
            self.final_result = str(result_text).strip()

        if event_data.get("is_error"):
            self.has_error = True

    def _format_tool_summary(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Format ringkasan pemanggilan tool agar mudah dibaca."""
        tool_lower = tool_name.lower()
        if "bash" in tool_lower:
            cmd = tool_input.get("command", "")
            return f"Bash ({cmd[:60]}...)" if len(cmd) > 60 else f"Bash ({cmd})"

        if any(w in tool_lower for w in ("read", "write", "edit", "view")):
            file_path = tool_input.get("file_path", "") or tool_input.get("target_file", "") or tool_input.get("path", "")
            base_name = file_path.split("/")[-1] if file_path else "berkas"
            return f"{tool_name} ({base_name})"

        if any(w in tool_lower for w in ("grep", "glob", "search")):
            query = tool_input.get("query", "") or tool_input.get("pattern", "") or tool_input.get("path", "")
            return f"{tool_name} ({query[:40]})" if query else tool_name

        if "codegraph" in tool_lower:
            query = tool_input.get("query", "")
            return f"CodeGraph ({query[:40]})" if query else "CodeGraph Explore"

        return tool_name

    def get_formatted_output(self) -> str:
        """
        Mengembalikan teks ringkasan hasil akhir eksekusi yang bersih untuk diserahkan ke Supervisor Serena.
        """
        if self.final_result:
            return self.final_result

        # Fallback jika event result tidak ditemukan tetapi ada tools yang dieksekusi
        if self.executed_tools:
            tools_list = "\n- ".join(self.executed_tools)
            return f"Tugas selesai diproses dengan aksi:\n- {tools_list}"

        return self.latest_activity
