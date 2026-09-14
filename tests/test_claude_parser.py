from app.services.claude_parser import ClaudeStreamParser

def test_parser_with_sample_events():
    parser = ClaudeStreamParser()

    # Event 1: Assistant text
    line1 = '{"type":"assistant","message":{"id":"1","type":"message","role":"assistant","content":[{"type":"text","text":"Memeriksa struktur proyek..."}]}}'
    update1 = parser.process_line(line1)
    assert update1 == "Memeriksa struktur proyek..."
    assert parser.latest_activity == "Memeriksa struktur proyek..."

    # Event 2: Assistant tool use (Bash)
    line2 = '{"type":"assistant","message":{"id":"2","type":"message","role":"assistant","content":[{"type":"tool_use","id":"call_1","name":"Bash","input":{"command":"git clone https://github.com/test/repo.git"}}]}}'
    update2 = parser.process_line(line2)
    assert "Bash (git clone https://github.com/test/repo.git)" in update2
    assert len(parser.executed_tools) == 1

    # Event 3: User tool result
    line3 = '{"type":"user","message":{"role":"user","content":[{"tool_use_id":"call_1","type":"tool_result","content":"Cloning into repo...","is_error":false}]}}'
    update3 = parser.process_line(line3)
    assert update3 is None
    assert parser.has_error is False

    # Event 4: Result event
    line4 = '{"type":"result","subtype":"success","result":"Repositori berhasil dikloning dan dikonfigurasi.","is_error":false}'
    update4 = parser.process_line(line4)
    assert update4 is None
    assert parser.final_result == "Repositori berhasil dikloning dan dikonfigurasi."

    formatted = parser.get_formatted_output()
    assert formatted == "Repositori berhasil dikloning dan dikonfigurasi."
    print("All ClaudeStreamParser tests passed successfully!")

if __name__ == "__main__":
    test_parser_with_sample_events()
