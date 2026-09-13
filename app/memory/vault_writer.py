import os
from datetime import datetime
import logging
import frontmatter
import re

from app import config

logger = logging.getLogger(__name__)

def append_to_daily_log(title: str, content: str) -> str:
    """
    Append an entry to today's Daily Log in the Obsidian Vault with a descriptive title format:
    Catatan Harian/YYYY-MM-DD - [Descriptive Title].md
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_time_str = datetime.now().strftime("%H:%M:%S")
    daily_log_dir = os.path.join(config.OBSIDIAN_VAULT_DIR, "Catatan Harian")
    os.makedirs(daily_log_dir, exist_ok=True)
    
    clean_title = title.strip() if title else "Catatan Harian"
    filename = f"{today_str}.md"
    file_path = os.path.join(daily_log_dir, filename)

    
    entry_header = f"\n\n### [{now_time_str}] {clean_title}\n\n"
    full_entry = entry_header + content.strip() + "\n"
    
    if os.path.exists(file_path):
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(full_entry)
    else:
        header_title = f"# {today_str} — Catatan Harian\n"

        post = frontmatter.Post(
            content=header_title + full_entry,
            tags=["daily-log", "second-brain"],
            date=today_str
        )
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
            
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"({now_str}) DailyLog entry appended: {file_path}")

    # Synchronize bi-directional backlinks to referenced WikiLinks in daily log entry
    try:
        sync_bi_directional_backlinks("Catatan Harian", filename, content)
    except Exception as e:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.warning(f"({now_str}) DailyLog backlink sync error: {e}")

    return file_path

def add_backlink_to_note(target_folder: str, target_filename: str, wikilink_to_add: str) -> bool:
    """
    Append a WikiLink under '## Konsep Terkait' section in target Obsidian note.
    """
    clean_target_name = target_filename[:-3] if target_filename.endswith(".md") else target_filename
    target_path = os.path.join(config.OBSIDIAN_VAULT_DIR, target_folder, f"{clean_target_name}.md")
    
    if not os.path.exists(target_path):
        for sub in ["Kotak Masuk", "Proyek Aktif", "Catatan Harian", "Profil & Keputusan", "Panduan & SOP"]:
            p = os.path.join(config.OBSIDIAN_VAULT_DIR, sub, f"{clean_target_name}.md")
            if os.path.exists(p):
                target_path = p
                break

    if not os.path.exists(target_path):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.warning(f"({now_str}) VaultWriter target note not found: {target_filename}")
        return False

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            target_post = frontmatter.load(f)
            
        target_content = target_post.content or ""
        clean_link_title = wikilink_to_add.strip("[").strip("]").split("/")[-1]
        
        if clean_link_title not in target_content and wikilink_to_add not in target_content:
            if "## Konsep Terkait" in target_content:
                updated = target_content.rstrip() + f"\n- {wikilink_to_add}\n"
            else:
                updated = target_content.rstrip() + f"\n\n## Konsep Terkait :\n- {wikilink_to_add}\n"
                
            target_post.content = updated
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(target_post))
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"({now_str}) VaultWriter backlink added to: {target_path}")
            return True
        return True
    except Exception as err:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.warning(f"({now_str}) VaultWriter error adding backlink to {target_path}: {err}")
        return False

def link_existing_notes(folder1: str, filename1: str, folder2: str, filename2: str) -> bool:
    """
    Establish bi-directional links between two existing notes in the Obsidian Vault.
    """
    clean_title1 = filename1[:-3] if filename1.endswith(".md") else filename1
    clean_title2 = filename2[:-3] if filename2.endswith(".md") else filename2
    
    wikilink1 = f"[[{folder1}/{clean_title1}]]"
    wikilink2 = f"[[{folder2}/{clean_title2}]]"
    
    res1 = add_backlink_to_note(folder1, filename1, wikilink2)
    res2 = add_backlink_to_note(folder2, filename2, wikilink1)
    return res1 and res2

def update_existing_note(folder: str, filename: str, additional_content: str, section_header: str = None) -> bool:
    """
    Contextually update or append new content/insights to an existing Obsidian note.
    If section_header is specified, appends content under that header or creates the header.
    """
    clean_target_name = filename[:-3] if filename.endswith(".md") else filename
    target_path = os.path.join(config.OBSIDIAN_VAULT_DIR, folder, f"{clean_target_name}.md")
    
    if not os.path.exists(target_path):
        for sub in ["Kotak Masuk", "Proyek Aktif", "Catatan Harian", "Profil & Keputusan", "Panduan & SOP"]:
            p = os.path.join(config.OBSIDIAN_VAULT_DIR, sub, f"{clean_target_name}.md")
            if os.path.exists(p):
                target_path = p
                break

    if not os.path.exists(target_path):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.warning(f"({now_str}) VaultWriter update note failed, target not found: {filename}")
        return False

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            target_post = frontmatter.load(f)
            
        target_content = target_post.content or ""
        
        if section_header:
            clean_header = section_header.strip("# ")
            header_pattern = rf"##\s+{re.escape(clean_header)}"
            if re.search(header_pattern, target_content, re.IGNORECASE):
                updated_content = target_content.rstrip() + f"\n- {additional_content.strip()}\n"
            else:
                updated_content = target_content.rstrip() + f"\n\n## {clean_header} :\n- {additional_content.strip()}\n"
        else:
            updated_content = target_content.rstrip() + f"\n\n{additional_content.strip()}\n"

        target_post.content = updated_content
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(target_post))
            
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"({now_str}) VaultWriter note contextually updated: {target_path}")
        return True
    except Exception as err:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.warning(f"({now_str}) VaultWriter error updating note {target_path}: {err}")
        return False

def link_notes_with_context(folder1: str, filename1: str, folder2: str, filename2: str, context_explanation: str) -> bool:
    """
    Link two notes with explicit contextual explanation of their relationship.
    """
    clean_title1 = filename1[:-3] if filename1.endswith(".md") else filename1
    clean_title2 = filename2[:-3] if filename2.endswith(".md") else filename2
    
    link_entry_for_1 = f"[[{folder2}/{clean_title2}]] — {context_explanation.strip()}"
    link_entry_for_2 = f"[[{folder1}/{clean_title1}]] — {context_explanation.strip()}"
    
    res1 = update_existing_note(folder1, filename1, link_entry_for_1, section_header="Konsep Terkait")
    res2 = update_existing_note(folder2, filename2, link_entry_for_2, section_header="Konsep Terkait")
    
    return res1 and res2

def link_multiple_notes(notes: list[tuple[str, str]], bi_directional: bool = True) -> bool:
    """
    Establish links between a list of multiple notes (each tuple is (folder, filename)).
    If bi_directional is True, links every note to every other note in the list.
    """
    if len(notes) < 2:
        return True
        
    all_success = True
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            folder1, filename1 = notes[i]
            folder2, filename2 = notes[j]
            if bi_directional:
                res = link_existing_notes(folder1, filename1, folder2, filename2)
            else:
                clean_title2 = filename2[:-3] if filename2.endswith(".md") else filename2
                wikilink2 = f"[[{folder2}/{clean_title2}]]"
                res = add_backlink_to_note(folder1, filename1, wikilink2)
            if not res:
                all_success = False
                
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"({now_str}) VaultWriter linked {len(notes)} notes (bi_directional={bi_directional})")
    return all_success



def sync_bi_directional_backlinks(new_note_folder: str, new_note_filename: str, content: str):
    """
    Parse content for WikiLinks [[TargetFolder/TargetFile]], locate target note files on disk,
    and append a clean backlink to the new note under ## Konsep Terkait section in target files.
    """
    if not content:
        return
        
    clean_new_title = new_note_filename[:-3] if new_note_filename.endswith(".md") else new_note_filename
    new_note_wikilink = f"[[{new_note_folder}/{clean_new_title}]]"
    
    matches = re.findall(r"\[\[([^\]]+)\]\]", content)
    for match in matches:
        target_ref = match.strip()
        if not target_ref:
            continue
            
        if "/" in target_ref:
            target_path = os.path.join(config.OBSIDIAN_VAULT_DIR, f"{target_ref}.md")
        else:
            target_path = None
            for sub in ["Kotak Masuk", "Proyek Aktif", "Catatan Harian", "Profil & Keputusan", "Panduan & SOP"]:
                p = os.path.join(config.OBSIDIAN_VAULT_DIR, sub, f"{target_ref}.md")
                if os.path.exists(p):
                    target_path = p
                    break
                    
        if target_path and os.path.exists(target_path):
            current_new_path = os.path.abspath(os.path.join(config.OBSIDIAN_VAULT_DIR, new_note_folder, f"{clean_new_title}.md"))
            if os.path.abspath(target_path) == current_new_path:
                continue
                
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    target_post = frontmatter.load(f)
                    
                target_content = target_post.content or ""
                if clean_new_title not in target_content:
                    if "## Konsep Terkait" in target_content:
                        updated = target_content.rstrip() + f"\n- {new_note_wikilink}\n"
                    else:
                        updated = target_content.rstrip() + f"\n\n## Konsep Terkait :\n- {new_note_wikilink}\n"
                        
                    target_post.content = updated
                    with open(target_path, "w", encoding="utf-8") as f:
                        f.write(frontmatter.dumps(target_post))
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    logger.info(f"({now_str}) VaultWriter bi-directional backlink synced to: {target_path}")
            except Exception as err:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.warning(f"({now_str}) VaultWriter backlink sync error: {err}")

def create_note(folder: str, filename: str, content: str, tags: list = None) -> str:
    """
    Create a markdown note inside specified Obsidian folder with clean frontmatter and 2-way backlinks.
    """
    target_dir = os.path.join(config.OBSIDIAN_VAULT_DIR, folder)
    os.makedirs(target_dir, exist_ok=True)
    
    if not filename.endswith(".md"):
        filename += ".md"
        
    file_path = os.path.join(target_dir, filename)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    post = frontmatter.Post(
        content=content.strip(),
        tags=tags or ["note"],
        date=today_str
    )
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
        
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"({now_str}) VaultWriter note created: {file_path}")

    # Synchronize 2-way bi-directional backlinks to referenced target notes
    try:
        sync_bi_directional_backlinks(folder, filename, content)
    except Exception as e:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.warning(f"({now_str}) VaultWriter bi-directional backlink error: {e}")

    return file_path

def read_note(folder: str, filename: str) -> str:
    """Read contents of an Obsidian markdown note."""
    if not filename.endswith(".md"):
        filename += ".md"
    file_path = os.path.join(config.OBSIDIAN_VAULT_DIR, folder, filename)
    if not os.path.exists(file_path):
        return f"Berkas catatan tidak ditemukan: {file_path}"
        
    with open(file_path, "r", encoding="utf-8") as f:
        post = frontmatter.load(f)
        return post.content

def get_user_profile() -> str:
    """
    Retrieve user personalization profile and explicit preferences from Obsidian (Profil & Keputusan/User_Profile.md).
    """
    file_path = os.path.join(config.OBSIDIAN_VAULT_DIR, "Profil & Keputusan", "User_Profile.md")
    if not os.path.exists(file_path):
        initial_profile = (
            "# Profil & Karakter Pengguna\n\n"
            "## Gaya Komunikasi & Berpikir :\n"
            "- Praktis, lugas, langsung pada poin inti tanpa basa-basi kaku.\n"
            "- Menyukai alur ide yang alami, autentik, dan tidak dibuat-buat.\n"
            "- Menghargai pemikiran terstruktur tetapi disampaikan secara humanis.\n\n"
            "## Fokus & Ide Utama :\n"
            "- Eksplorasi teknologi, infrastruktur, otomasi, dan efisiensi alur kerja.\n"
            "- Pengorganisasian ide dan catatan harian secara alami pada Obsidian Second Brain.\n\n"
            "## Catatan Evolusi Profil :\n"
            "- (Profil ini berkembang secara dinamis seiring bertambahnya interaksi)\n"
        )
        create_note("Profil & Keputusan", "User_Profile.md", initial_profile, tags=["user-profile", "preferences"])
        return initial_profile
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            post = frontmatter.load(f)
            return post.content
    except Exception:
        return ""

def update_user_profile(new_insight: str) -> str:
    """
    Dynamically append a new character trait, habit, or preference insight to User_Profile.md.
    """
    file_path = os.path.join(config.OBSIDIAN_VAULT_DIR, "Profil & Keputusan", "User_Profile.md")
    current_content = get_user_profile()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    insight_entry = f"\n- [{today_str}] {new_insight.strip()}"
    updated_content = current_content.strip() + insight_entry + "\n"
    
    return create_note("Profil & Keputusan", "User_Profile.md", updated_content, tags=["user-profile", "preferences"])

def save_skill(skill_name: str, content: str, tags: list = None) -> str:
    """
    Save or update a dynamic Skill SOP note in Obsidian Vault (Panduan & SOP/<skill_name>.md).
    """
    clean_name = skill_name.strip().lower().replace(" ", "_")
    if not clean_name.endswith(".md"):
        clean_name += ".md"
    
    skill_tags = (tags or []) + ["skill", "serena-skill"]
    file_path = create_note("Panduan & SOP", clean_name, content, tags=skill_tags)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"({now_str}) VaultWriter skill saved: {file_path}")
    return f"Skill berhasil disimpan di: {file_path}"

def list_skills() -> list:
    """
    List all available dynamic Skill SOP notes in Obsidian Vault (Panduan & SOP).
    """
    skills_dir = os.path.join(config.OBSIDIAN_VAULT_DIR, "Panduan & SOP")
    if not os.path.exists(skills_dir):
        return []
    
    skills = []
    for f in os.listdir(skills_dir):
        if f.endswith(".md"):
            skills.append(f[:-3])
    return sorted(skills)

def get_skill(skill_name: str) -> str:
    """
    Retrieve content of a specific Skill SOP note from Obsidian Vault (Panduan & SOP/<skill_name>.md).
    """
    clean_name = skill_name.strip().lower().replace(" ", "_")
    if not clean_name.endswith(".md"):
        clean_name += ".md"
    return read_note("Panduan & SOP", clean_name)

def save_concept_note(title: str, content: str, folder: str = "Kotak Masuk", tags: list = None) -> str:
    """
    Save or merge a concept note in Obsidian Vault with automated LlamaIndex parent lookup,
    Smart Note Merging into existing concept notes, and 2-way backlinks.
    """
    from app.memory import obsidian_engine
    
    clean_title = title.strip()
    if clean_title.endswith(".md"):
        filename = clean_title
        clean_title = clean_title[:-3]
    else:
        filename = f"{clean_title}.md"

    # Step 1: Check if LlamaIndex finds a parent concept note to link or merge
    try:
        parent_note = obsidian_engine.find_parent_concept_note(clean_title)
        if parent_note:
            parent_folder = parent_note["folder"]
            parent_filename = parent_note["filename"]
            parent_title = parent_note["title"]
            
            # Sub-topic splitting: Jika judul sub-topik berbeda dengan judul induk, buat catatan atomik terpisah & hubungkan 2 arah (bi-directional link)
            if clean_title and clean_title.lower() != parent_title.lower():
                full_body = content.strip()
                if not full_body.startswith(f"# {clean_title}"):
                    full_body = f"# {clean_title}\n\n{full_body}"
                
                full_body += f"\n\n## Konsep Terkait :\n- [[{parent_title}]] — Konsep induk / konteks utama."
                
                # Buat catatan atomik terpisah untuk sub-topik
                new_note_path = create_note(folder, filename, full_body, tags=tags or ["brainstorming", "konsep", "subtopik", "second-brain"])
                
                # Tambahkan backlink pada catatan induk menuju sub-topik ini
                add_backlink_to_note(parent_folder, parent_filename, f"[[{clean_title}]] — Sub-topik spesifik.")
                
                append_to_daily_log(title=f"Catatan Konsep: {clean_title} (Sub-topik: {parent_title})", content=content)
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"({now_str}) Created split atomic sub-topic note: {new_note_path} (linked to parent {parent_title})")
                return new_note_path
            else:
                # Merge langsung ke catatan induk jika judul identik (penyempurnaan materi konsep yang sama)
                merged = update_existing_note(parent_folder, parent_filename, content.strip(), section_header="Materi Diskusi Lanjutan")
                if merged:
                    parent_path = os.path.join(config.OBSIDIAN_VAULT_DIR, parent_folder, parent_filename)
                    append_to_daily_log(title=f"Update Konsep: {parent_title}", content=content)
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    logger.info(f"({now_str}) Merged concept refinement into parent note: {parent_path}")
                    return parent_path
    except Exception as err:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.warning(f"({now_str}) Smart merge/split lookup warning: {err}")


    # Step 2: If no parent note exists, create a new concept note
    clean_body = content.strip()
    if clean_body.startswith(f"# {clean_title}"):
        full_content = clean_body
    else:
        full_content = f"# {clean_title}\n\n{clean_body}"
    
    try:
        rel_notes = obsidian_engine.search_obsidian_vault(clean_title + " " + content, top_k=2)
        if rel_notes and "WikiLink Target: [[" in rel_notes:
            matches = re.findall(r"WikiLink Target:\s*\[\[([^\]]+)\]\]", rel_notes)
            context_links = []
            seen_targets = set()
            for target in matches:
                clean_target = target.strip()
                if clean_target != clean_title and clean_target not in full_content and clean_target not in seen_targets:
                    seen_targets.add(clean_target)
                    context_links.append(f"- [[{clean_target}]] — Konsep terkait relevan di Vault.")
            if context_links:
                full_content += "\n\n## Konsep Terkait :\n" + "\n".join(context_links)
    except Exception as err:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.warning(f"({now_str}) VaultWriter concept note search error: {err}")
        
    file_path = create_note(folder, filename, full_content, tags=tags or ["brainstorming", "konsep", "second-brain"])
    append_to_daily_log(title=f"Catatan Konsep: {clean_title}", content=full_content)
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"({now_str}) Concept note saved to Obsidian: {file_path}")
    return file_path




