import asyncio
import os
import shutil
import logging
import time
from typing import Callable, Awaitable, Optional

from app import config
from app.services.claude_parser import ClaudeStreamParser

logger = logging.getLogger(__name__)

def find_claude_cli() -> Optional[str]:
    """Locate the executable path for the Claude Code CLI."""
    cli_path = shutil.which("claude")
    if cli_path:
        return cli_path
    
    home = os.path.expanduser("~")
    possible_paths = [
        os.path.join(home, ".nvm", "versions", "node", "current", "bin", "claude"),
        os.path.join(home, ".local", "bin", "claude"),
        "/usr/local/bin/claude",
        "/usr/bin/claude"
    ]
    for path in possible_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
            
    return None

async def execute_claude_task(
    prompt: str,
    progress_callback: Optional[Callable[[str, int], Awaitable[None]]] = None,
    cwd: Optional[str] = None,
    timeout_seconds: int = 1800
) -> str:
    """
    Execute a prompt using Claude Code CLI asynchronously with stream-json parsing and live updates.
    """
    cli_path = find_claude_cli()
    if not cli_path:
        raise FileNotFoundError(
            "Perintah 'claude' CLI tidak ditemukan di sistem. "
            "Pastikan Claude Code telah terpasang dan dapat diakses dari terminal."
        )

    target_cwd = cwd or config.SERENA_PROJECTS_DIR
    if not os.path.exists(target_cwd):
        os.makedirs(target_cwd, exist_ok=True)

    system_instructions = (
        "Aturan Persona: Jawablah dalam bahasa Indonesia dengan sopan, santun, dan profesional. "
        "DILARANG MENGGUNAKAN EMOJI SAMA SEKALI dalam balasan Anda. "
        f"Direktori Root Agent Workspace Proyek: {config.SERENA_PROJECTS_DIR}.\n"
        "Aturan Penempatan Berkas: Seluruh tugas koding, pembuatan berkas, dan proyek baru WAJIB ditempatkan di dalam folder proyek spesifik di bawah direktori Agent Workspace (contoh: " + config.SERENA_PROJECTS_DIR + "/<nama_proyek>/).\n"
        "PERINTAH EKSEKUSI MUTLAK:\n"
        "Anda memiliki izin penuh untuk mengeksekusi perintah terminal / bash. EKSEKUSI LANGSUNG seluruh perintah (seperti git clone, penulisan berkas .env, inisialisasi codegraph, dsb.) menggunakan tools yang tersedia.\n"
        "DILARANG KERAS hanya menuliskan teks kode bash atau meminta konfirmasi manual pengguna tanpa menjalankan peralatannya!\n\n"
        f"Instruksi Pengguna: {prompt}"
    )

    cmd = [
        cli_path,
        "--dangerously-skip-permissions",
        "-p", system_instructions,
        "--output-format", "stream-json",
        "--verbose"
    ]
    
    logger.info(f"Menjalankan perintah Claude Code di {target_cwd}: {prompt[:50]}...")
    
    start_time = time.time()
    last_update_time = start_time
    parser = ClaudeStreamParser()

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=target_cwd
    )

    raw_lines = []
    
    async def read_stream():
        nonlocal last_update_time
        if process.stdout is None:
            return
            
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            
            line_str = line_bytes.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue

            raw_lines.append(line_str)
            activity_update = parser.process_line(line_str)

            now = time.time()
            if activity_update and progress_callback:
                elapsed = int(now - start_time)
                try:
                    await progress_callback(activity_update, elapsed)
                except Exception as e:
                    logger.debug(f"Kendala callback status kemajuan: {e}")

    try:
        await asyncio.wait_for(read_stream(), timeout=timeout_seconds)
        stderr_bytes = await process.stderr.read() if process.stderr else b""
        await process.wait()
        
        stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
        formatted_output = parser.get_formatted_output()
        
        # Tangani jika output kosong dan terdapat pesan error di stderr
        if not formatted_output and stderr_str:
            formatted_output = f"Catatan Sistem / Error:\n{stderr_str}"
            
        if process.returncode != 0 and not formatted_output:
            formatted_output = f"Proses berakhir dengan kode status {process.returncode}.\n{stderr_str}"
            
        return formatted_output
        
    except asyncio.TimeoutError:
        try:
            process.kill()
        except Exception:
            pass
        raise TimeoutError(f"Waktu eksekusi melebihi batas {timeout_seconds // 60} menit.")
