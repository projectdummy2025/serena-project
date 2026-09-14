import os
import re
import asyncio
import logging
from typing import Dict, Any, Optional

from app import config

logger = logging.getLogger(__name__)

def resolve_project_path(project_name: str) -> str:
    """
    Memvalidasi dan mengembalikan jalur direktori proyek yang aman di dalam root agent workspace.
    Mencegah path traversal untuk menjaga keamanan sistem.
    """
    clean_name = re.sub(r"[^\w\-\.]", "_", project_name.strip())
    target_path = os.path.abspath(os.path.join(config.SERENA_PROJECTS_DIR, clean_name))

    # Pastikan jalur berada di dalam direktori proyek yang diizinkan
    allowed_root = os.path.abspath(config.SERENA_PROJECTS_DIR)
    if not target_path.startswith(allowed_root):
        raise ValueError(f"Akses direktori di luar batas tidak diizinkan: {target_path}")

    return target_path

async def execute_linux_command(
    command: str,
    cwd: Optional[str] = None,
    timeout_seconds: int = 120
) -> Dict[str, Any]:
    """
    Mengeksekusi perintah shell Linux secara langsung dan mengembalikan hasil keluaran.
    Berjalan cepat secara native tanpa overhead AI LLM.
    """
    target_directory = cwd or config.SERENA_PROJECTS_DIR
    if not os.path.exists(target_directory):
        os.makedirs(target_directory, exist_ok=True)

    logger.info(f"Worker System menjalankan perintah di {target_directory}: {command[:60]}")

    try:
        # Jalankan proses shell secara asynchronous
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=target_directory
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds
        )

        stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
        exit_code = process.returncode

        is_success = (exit_code == 0)
        output_text = stdout_text if stdout_text else stderr_text

        return {
            "success": is_success,
            "exit_code": exit_code,
            "output": output_text,
            "error": stderr_text if not is_success else ""
        }

    except asyncio.TimeoutError:
        try:
            process.kill()
        except Exception:
            pass
        return {
            "success": False,
            "exit_code": -1,
            "output": "",
            "error": f"Batas waktu eksekusi ({timeout_seconds} detik) telah terlampaui."
        }
    except Exception as err:
        return {
            "success": False,
            "exit_code": -1,
            "output": "",
            "error": f"Kendala eksekusi sistem: {str(err)}"
        }

async def clone_project_repo(repo_url: str, project_name: str) -> Dict[str, Any]:
    """
    Mengkloning repositori Git ke folder proyek khusus di bawah root agent workspace.
    """
    project_path = resolve_project_path(project_name)

    if os.path.exists(project_path) and os.listdir(project_path):
        return {
            "success": True,
            "project_path": project_path,
            "output": f"Direktori proyek sudah ada di {project_path}."
        }

    clone_command = f"git clone {repo_url} {project_path}"
    result = await execute_linux_command(clone_command, cwd=config.SERENA_PROJECTS_DIR, timeout_seconds=180)

    if result["success"]:
        result["project_path"] = project_path

    return result

def write_project_env(project_name: str, env_content: str) -> Dict[str, Any]:
    """
    Menulis berkas konfigurasi .env tepat di dalam direktori proyek target.
    """
    project_path = resolve_project_path(project_name)
    os.makedirs(project_path, exist_ok=True)

    env_path = os.path.join(project_path, ".env")
    try:
        with open(env_path, "w", encoding="utf-8") as file_handle:
            file_handle.write(env_content.strip() + "\n")

        return {
            "success": True,
            "env_path": env_path,
            "output": f"Berkas .env berhasil dipasang di {env_path}."
        }
    except Exception as err:
        return {
            "success": False,
            "env_path": "",
            "output": f"Gagal menulis berkas .env: {str(err)}"
        }

async def init_project_codegraph(project_name: str) -> Dict[str, Any]:
    """
    Menjalankan inisialisasi codegraph init pada direktori proyek target.
    """
    project_path = resolve_project_path(project_name)
    if not os.path.exists(project_path):
        return {
            "success": False,
            "output": f"Direktori proyek belum ditemukan di {project_path}."
        }

    return await execute_linux_command("codegraph init", cwd=project_path, timeout_seconds=120)

async def setup_full_project(
    repo_url: str,
    project_name: str,
    env_content: Optional[str] = None
) -> Dict[str, Any]:
    """
    Alur satu langkah untuk kloning repositori, penulisan .env, dan inisialisasi codegraph.
    """
    # 1. Kloning repositori git
    clone_result = await clone_project_repo(repo_url, project_name)
    if not clone_result["success"]:
        return clone_result

    project_path = clone_result.get("project_path", resolve_project_path(project_name))

    # 2. Tulis berkas .env jika disediakan
    env_status = "Berkas .env tidak disertakan."
    if env_content and env_content.strip():
        write_result = write_project_env(project_name, env_content)
        env_status = write_result["output"]

    # 3. Jalankan inisialisasi codegraph
    codegraph_result = await init_project_codegraph(project_name)
    codegraph_status = codegraph_result.get("output", "Codegraph init selesai.")

    return {
        "success": True,
        "project_path": project_path,
        "clone_output": clone_result.get("output", "Kloning berhasil."),
        "env_output": env_status,
        "codegraph_output": codegraph_status
    }
