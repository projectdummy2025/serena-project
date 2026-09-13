import asyncio
import os
import shutil
import logging
import time
from typing import Callable, Awaitable, Optional

from app import config

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
    Execute a prompt using Claude Code CLI asynchronously and stream stdout live.
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
        "Jika pengguna bertanya atau mengobrol biasa, jawablah secara langsung dan alami. "
        "Jika pengguna memberikan tugas pemrograman atau pengeditan berkas, laksanakan tugas tersebut dan berikan laporan ringkas hasilnya.\n\n"
        f"Instruksi Pengguna: {prompt}"
    )

    
    cmd = [cli_path, "-p", system_instructions]
    
    logger.info(f"Menjalankan perintah Claude Code di {target_cwd}: {prompt[:50]}...")
    
    start_time = time.time()
    last_update_time = start_time
    latest_activity = "Memulai proses eksekusi instruksi..."

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=target_cwd
    )

    output_lines = []
    
    async def read_stream():
        nonlocal latest_activity, last_update_time
        if process.stdout is None:
            return
            
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            
            line_str = line_bytes.decode("utf-8", errors="replace").strip()
            if line_str:
                output_lines.append(line_str)
                if len(line_str) > 5 and not line_str.startswith("http"):
                    latest_activity = line_str[:120]

            now = time.time()
            if progress_callback and (now - last_update_time >= 5.0):
                last_update_time = now
                elapsed = int(now - start_time)
                try:
                    await progress_callback(latest_activity, elapsed)
                except Exception as e:
                    logger.debug(f"Kendala saat memperbarui status kemajuan: {e}")

    try:
        await asyncio.wait_for(read_stream(), timeout=timeout_seconds)
        stderr_bytes = await process.stderr.read() if process.stderr else b""
        await process.wait()
        
        stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
        
        full_output = "\n".join(output_lines).strip()
        if not full_output and stderr_str:
            full_output = f"Catatan Sistem / Error:\n{stderr_str}"
            
        if process.returncode != 0 and not full_output:
            full_output = f"Proses berakhir dengan kode status {process.returncode}.\n{stderr_str}"
            
        return full_output
        
    except asyncio.TimeoutError:
        try:
            process.kill()
        except Exception:
            pass
        raise TimeoutError(f"Waktu eksekusi melebihi batas {timeout_seconds // 60} menit.")
