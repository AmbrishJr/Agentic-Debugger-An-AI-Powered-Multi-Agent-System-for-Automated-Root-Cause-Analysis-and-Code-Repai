"""Trusted entrypoint inside the Vercel VM only; limits precede untrusted imports."""
import os
import resource
import sys

if os.getuid() != 65534:
    raise SystemExit('Runner image must use the unprivileged 65534 user.')
os.environ.clear()
os.environ.update(PATH='/usr/local/bin:/usr/bin:/bin', HOME='/tmp', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
os.umask(0o077)
for limit, value in ((resource.RLIMIT_AS, 256 * 1024 * 1024), (resource.RLIMIT_NPROC, 32),
                     (resource.RLIMIT_NOFILE, 128), (resource.RLIMIT_FSIZE, 16 * 1024 * 1024),
                     (resource.RLIMIT_CORE, 0), (resource.RLIMIT_CPU, 120)):
    resource.setrlimit(limit, (value, value))
sys.path.insert(0, '/opt/autorca')
from bootstrap import main

raise SystemExit(main())
