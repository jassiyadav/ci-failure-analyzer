"""Hand-labelled failure cases. Extend this to 30-40 by breaking your own pipelines on purpose."""

CASES = [
    {
        "id": "node-missing-module",
        "expected_category": "dependency",
        "log": """> app@1.0.0 test
> jest
Error: Cannot find module 'express'
Require stack:
- /home/runner/work/app/app/src/server.js
##[error]Process completed with exit code 1.""",
    },
    {
        "id": "pytest-assertion",
        "expected_category": "test_failure",
        "log": """============ FAILURES ============
____ test_create_todo ____
    def test_create_todo(client):
>       assert resp.status_code == 201
E       assert 500 == 201
FAILED tests/test_api.py::test_create_todo - assert 500 == 201
========= 1 failed, 4 passed in 0.82s =========
##[error]Process completed with exit code 1.""",
    },
    {
        "id": "docker-copy-missing-file",
        "expected_category": "build_config",
        "log": """#8 [4/6] COPY requirements.txt .
#8 ERROR: failed to calculate checksum of ref: "/requirements.txt": not found
ERROR: failed to solve: failed to compute cache key: "/requirements.txt": not found
##[error]Process completed with exit code 1.""",
    },
    {
        "id": "eslint-unused-var",
        "expected_category": "lint",
        "log": """> eslint src/
/home/runner/work/app/app/src/utils.js
  12:7  error  'x' is assigned a value but never used  no-unused-vars
✖ 1 problem (1 error, 0 warnings)
##[error]Process completed with exit code 1.""",
    },
    {
        "id": "docker-login-denied",
        "expected_category": "secrets_permissions",
        "log": """Error response from daemon: Get "https://registry-1.docker.io/v2/": unauthorized: incorrect username or password
##[error]Process completed with exit code 1.""",
    },
    {
        "id": "db-connection-refused",
        "expected_category": "infra",
        "log": """Error: connect ECONNREFUSED 127.0.0.1:5432
    at TCPConnectWrap.afterConnect [as oncomplete] (node:net:1555:16)
##[error]Process completed with exit code 1.""",
    },
    {
        # Hard case: no obvious keyword, the baseline should miss it and a real LLM should not.
        "id": "missing-env-var",
        "expected_category": "build_config",
        "log": """Error: Missing required environment variable DATABASE_URL
    at loadConfig (config.js:8:11)
    at Object.<anonymous> (server.js:3:1)
##[error]Process completed with exit code 1.""",
    },
]
