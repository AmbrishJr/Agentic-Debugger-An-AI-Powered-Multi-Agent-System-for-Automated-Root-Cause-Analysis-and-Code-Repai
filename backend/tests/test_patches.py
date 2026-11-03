from app.services.patches import unified_patch


def test_diff_preserves_missing_final_newlines():
    patch = unified_patch('module.py', 'value = 1', 'value = 2')
    assert '-value = 1\n\\ No newline at end of file\n' in patch
    assert '+value = 2\n\\ No newline at end of file\n' in patch
    assert patch.count('No newline at end of file') == 2


def test_newline_only_change_is_visible():
    patch = unified_patch('module.py', 'value = 1', 'value = 1\n')
    assert '-value = 1\n\\ No newline at end of file\n+value = 1\n' in patch
