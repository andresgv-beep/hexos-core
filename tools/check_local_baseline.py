"""Offline baseline. Never import the opt-in live-model/NAS scripts.

Run from any directory: python3 tools/check_local_baseline.py
The explicit allowlist prevents a newly added live probe from contacting the
user's running chat just because its filename ends in _test.py.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
MODULES = '''agent_chat catalog containers continuity conversation credential_request
devices document_reading fact_extraction file_catalog hosts internal_tasks
listing_continuity media_chat media_encoder media_files media_jobs media_layout
media_native_session media_reviews media_selection media_snapshot model_lifecycle
muletas nas_directories nas_file_access nas_files nas_session native_adapter
native_channels native_progress native_tools_parser network notes output_continuity
procedures profile_memory recall search_contract senaladores
ssh_diagnostics text_media_reply thinking_toggle trace ventana_contexto web_actual
web_read_guidance web work'''.split()

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        ['tools.' + name + '_test' for name in MODULES])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(not result.wasSuccessful())
