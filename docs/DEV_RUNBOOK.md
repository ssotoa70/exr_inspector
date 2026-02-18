# exr-inspector: Development Runbook

**For developers performing local testing, iteration, and pre-commit validation**

Estimated total setup time: 15-20 minutes. No VAST infrastructure required.

---

## Table of Contents

1. [Environment Setup (5 min)](#environment-setup)
2. [Local Development](#local-development)
3. [Running Tests (3-5 min)](#running-tests)
4. [Local Debugging](#local-debugging)
5. [Mock Data & Testing Scenarios](#mock-data--testing-scenarios)
6. [Pre-Commit Checklist](#pre-commit-checklist)

---

## Environment Setup

**Estimated Time: 5 minutes**

### System Requirements

You need:

- **Python**: 3.9 or 3.10 (3.11+ not recommended due to tokenizer compatibility)
- **Git**: For cloning and committing
- **pip**: Python package manager (included with Python)
- **Text Editor/IDE**: VS Code, PyCharm, etc. (optional)

### Step 1: Clone Repository and Navigate

```bash
cd /path/to/exr-inspector
git status
```

Expected output:
```
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
```

### Step 2: Create Virtual Environment

```bash
# Create venv
python3 -m venv venv

# Activate venv
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate     # Windows

# Verify activation (prompt should show (venv))
which python
```

Expected output:
```
/path/to/exr-inspector/venv/bin/python
```

### Step 3: Install Dependencies

```bash
# Install development dependencies
pip install -r functions/exr_inspector/requirements.txt

# Install test dependencies
pip install pytest pytest-cov pytest-mock

# Verify installations
python -c "import OpenImageIO; print(f'OpenImageIO: {OpenImageIO.__version__}')"
python -c "import pyarrow; print(f'PyArrow: {pyarrow.__version__}')"
```

Expected output:
```
OpenImageIO: 2.4.X or later
PyArrow: 10.0.0 or later
```

### Step 4: Verify Setup

```bash
# Run a quick smoke test
python -m pytest functions/exr_inspector/test_vast_db_persistence.py::TestVectorEmbeddings::test_metadata_embedding_dimension -v
```

Expected output:
```
test_metadata_embedding_dimension PASSED [100%]
```

---

## Local Development

### Project Structure

```
exr-inspector/
├── functions/exr_inspector/
│   ├── main.py                          # Handler entry point
│   ├── vast_db_persistence.py           # Database integration
│   ├── test_vast_db_persistence.py      # Unit tests (45+ tests, no cluster needed)
│   ├── requirements.txt                 # Python dependencies
│   ├── Aptfile                          # System libraries
│   └── README.md                        # Function documentation
├── docs/
│   ├── QUICK_START_VAST.md              # Production deployment guide
│   ├── TROUBLESHOOTING.md               # Issue resolution
│   ├── VECTOR_STRATEGY.md               # Embedding details
│   └── DEV_RUNBOOK.md                   # This file
├── vast_schemas.py                      # Database schema definitions
├── README.md                            # Project overview
└── PRD.md                               # Product requirements
```

### Key Modules

**main.py** - VAST DataEngine handler
- Entry point for serverless invocations
- Parses configuration from event payload
- Calls EXR inspection and persistence

**vast_db_persistence.py** - Database layer
- Vector embedding computation (deterministic, 384D)
- PyArrow table conversion
- Idempotent upsert logic
- Error handling and logging

**test_vast_db_persistence.py** - Test suite
- 45+ unit tests
- Mock sessions (no VAST cluster needed)
- Coverage: embeddings, conversion, errors

### Making Code Changes

1. **Edit code in venv**:
   ```bash
   # Example: modify vast_db_persistence.py
   nano functions/exr_inspector/vast_db_persistence.py
   ```

2. **Test immediately** (see [Running Tests](#running-tests))

3. **Check before commit** (see [Pre-Commit Checklist](#pre-commit-checklist))

---

## Running Tests

**Estimated Time: 3-5 minutes**

### Quick Test (30 seconds)

Run core vector embedding tests:

```bash
cd functions/exr_inspector
python -m pytest test_vast_db_persistence.py::TestVectorEmbeddings -v
```

Expected output:
```
test_metadata_embedding_determinism PASSED
test_metadata_embedding_unit_norm PASSED
test_metadata_embedding_dimension PASSED
test_metadata_embedding_different_payloads PASSED
test_channel_fingerprint_determinism PASSED
test_channel_fingerprint_unit_norm PASSED
====================== 6 passed in 0.85s ======================
```

### Medium Test (1-2 minutes)

Run all unit tests:

```bash
cd functions/exr_inspector
python -m pytest test_vast_db_persistence.py -v
```

Expected output:
```
test_metadata_embedding_determinism PASSED
test_metadata_embedding_unit_norm PASSED
test_metadata_embedding_dimension PASSED
... (40+ more tests)
====================== 45 passed in 4.23s ======================
```

### Full Test with Coverage (2-3 minutes)

```bash
cd functions/exr_inspector
python -m pytest test_vast_db_persistence.py --cov=vast_db_persistence --cov-report=term-missing
```

Expected output:
```
vast_db_persistence.py    487    45    91%
====================== 45 passed in 5.12s ======================

Name                    Stmts   Miss  Cover   Missing
-----------------------------------------------------
vast_db_persistence.py  487    45    91%   (list of uncovered lines)
```

Success criteria:
- Coverage > 85%
- All tests pass
- No import errors

### Test Only Integration Features (1 minute)

```bash
cd functions/exr_inspector
python -m pytest test_vast_db_persistence.py::TestPersistence -v
```

Expected output:
```
test_persist_new_file_success PASSED
test_persist_existing_file_updates_timestamp PASSED
test_persist_missing_session_skips PASSED
test_persist_error_handling PASSED
====================== 4 passed in 1.23s ======================
```

### Debugging Test Failures

If a test fails:

```bash
# Run with verbose output and stop on first failure
python -m pytest test_vast_db_persistence.py -vv -x

# Run with print statements visible
python -m pytest test_vast_db_persistence.py -s

# Run with full traceback
python -m pytest test_vast_db_persistence.py -vv --tb=long
```

---

## Local Debugging

### Interactive Python Session

Test your changes interactively:

```bash
cd functions/exr_inspector
python3
```

Then in the Python shell:

```python
# Import modules
from vast_db_persistence import compute_metadata_embedding, compute_channel_fingerprint

# Test embedding computation
payload = {
    "file": {
        "path": "/data/test.exr",
        "multipart_count": 2,
        "is_deep": False,
        "size_bytes": 1048576,
    },
    "channels": [
        {"name": "R", "type": "float", "x_sampling": 1, "y_sampling": 1},
        {"name": "G", "type": "float", "x_sampling": 1, "y_sampling": 1},
        {"name": "B", "type": "float", "x_sampling": 1, "y_sampling": 1},
        {"name": "A", "type": "float", "x_sampling": 1, "y_sampling": 1},
    ],
    "parts": [
        {
            "part_index": 0,
            "compression": "zip",
            "is_tiled": False,
            "tile_width": 0,
            "tile_height": 0,
        }
    ],
}

# Compute embedding
embedding = compute_metadata_embedding(payload)
print(f"Embedding size: {len(embedding)}D")
print(f"First 10 values: {embedding[:10]}")

# Check norm
norm = sum(v * v for v in embedding) ** 0.5
print(f"L2 norm: {norm:.9f}")  # Should be ~1.0

# Exit
exit()
```

Expected output:
```
Embedding size: 384D
First 10 values: [0.05..., 0.05..., ...]
L2 norm: 1.000000000
```

### Debug Logging

Enable verbose logging:

```python
# In test or script
import logging

# Set to DEBUG level
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('vast_db_persistence').setLevel(logging.DEBUG)

# Now import and run code
from vast_db_persistence import compute_metadata_embedding
embedding = compute_metadata_embedding(payload)

# Will print detailed debug messages
```

### Inspect Specific Functions

```python
from vast_db_persistence import (
    _normalize_path,
    _extract_metadata_features,
    payload_to_files_row,
)
import json

# Test path normalization
path = "/renders//shot_001.exr"
normalized = _normalize_path(path)
print(f"Normalized: {normalized}")

# Test feature extraction
payload = {...}
features = _extract_metadata_features(payload)
print(json.dumps(features, indent=2))

# Test PyArrow conversion
files_row = payload_to_files_row(payload, [0.1] * 384)
print(f"Table schema: {files_row.schema}")
print(f"Columns: {files_row.column_names}")
```

---

## Mock Data & Testing Scenarios

### Scenario 1: Minimal EXR (Single Channel, No Multipart)

```python
from vast_db_persistence import compute_metadata_embedding, payload_to_files_row
import json

payload = {
    "file": {
        "path": "/renders/simple.exr",
        "size_bytes": 524288,
        "mtime": "2025-02-06T10:30:00Z",
        "multipart_count": 1,
        "is_deep": False,
    },
    "channels": [
        {"name": "Y", "type": "float", "x_sampling": 1, "y_sampling": 1},
    ],
    "parts": [
        {
            "part_index": 0,
            "part_name": "default",
            "compression": "none",
            "is_tiled": False,
            "tile_width": 0,
            "tile_height": 0,
        }
    ],
    "attributes": {},
}

# Compute embedding
embedding = compute_metadata_embedding(payload)
print(f"✓ Embedding computed: {len(embedding)}D")

# Convert to PyArrow
files_row = payload_to_files_row(payload, embedding)
print(f"✓ PyArrow conversion successful")
```

### Scenario 2: Complex EXR (Multi-Part, Deep)

```python
payload = {
    "file": {
        "path": "/renders/complex_deep.exr",
        "size_bytes": 10485760,  # 10 MB
        "mtime": "2025-02-06T15:45:00Z",
        "multipart_count": 3,
        "is_deep": True,
    },
    "channels": [
        {"name": "R", "type": "float", "x_sampling": 1, "y_sampling": 1},
        {"name": "G", "type": "float", "x_sampling": 1, "y_sampling": 1},
        {"name": "B", "type": "float", "x_sampling": 1, "y_sampling": 1},
        {"name": "A", "type": "float", "x_sampling": 1, "y_sampling": 1},
        {"name": "Z", "type": "float", "x_sampling": 1, "y_sampling": 1},
        {"name": "ZBack", "type": "float", "x_sampling": 1, "y_sampling": 1},
        {"name": "diffuse.R", "type": "float", "x_sampling": 1, "y_sampling": 1},
        {"name": "diffuse.G", "type": "float", "x_sampling": 1, "y_sampling": 1},
    ],
    "parts": [
        {
            "part_index": 0,
            "part_name": "beauty",
            "compression": "zip",
            "is_tiled": True,
            "tile_width": 64,
            "tile_height": 64,
        },
        {
            "part_index": 1,
            "part_name": "diffuse",
            "compression": "piz",
            "is_tiled": True,
            "tile_width": 64,
            "tile_height": 64,
        },
        {
            "part_index": 2,
            "part_name": "specular",
            "compression": "rle",
            "is_tiled": False,
            "tile_width": 0,
            "tile_height": 0,
        },
    ],
    "attributes": {
        "viewingDirection": "[0, 0, -1]",
        "aperture": "2.8",
        "focalLength": "50",
    },
}

embedding = compute_metadata_embedding(payload)
print(f"✓ Complex payload processed: {len(embedding)}D embedding")
```

### Scenario 3: Idempotent Upsert (Same File Twice)

```python
from vast_db_persistence import persist_to_vast_database
from unittest.mock import MagicMock

# Create mock session
mock_session = MagicMock()
mock_session.table.return_value = MagicMock()

event = {
    "vastdb_endpoint": "mock-endpoint",
    "vastdb_access_key": "mock-key",
    "vastdb_secret_key": "mock-secret",
}

# First insertion
result1 = persist_to_vast_database(payload, event)
print(f"First insert status: {result1.get('status')}")

# Second insertion (identical payload)
result2 = persist_to_vast_database(payload, event)
print(f"Second insert status: {result2.get('status')}")

# Both should succeed (idempotent)
print(f"✓ Idempotent upsert working")
```

### Scenario 4: Error Cases

```python
from vast_db_persistence import compute_metadata_embedding, VectorEmbeddingError

# Test 1: Missing required key
try:
    bad_payload = {"channels": []}  # Missing "file"
    embedding = compute_metadata_embedding(bad_payload)
except Exception as e:
    print(f"✓ Caught error for missing key: {type(e).__name__}")

# Test 2: Malformed channel
try:
    bad_payload = {
        "file": {"multipart_count": 1},
        "channels": [{"name": "R"}],  # Missing "type"
        "parts": [],
    }
    embedding = compute_metadata_embedding(bad_payload)
except Exception as e:
    print(f"✓ Caught error for malformed channel: {type(e).__name__}")

# Test 3: Empty payload (degenerate case)
try:
    minimal_payload = {
        "file": {"multipart_count": 1},
        "channels": [],
        "parts": [],
    }
    embedding = compute_metadata_embedding(minimal_payload)
    norm = sum(v * v for v in embedding) ** 0.5
    print(f"✓ Minimal payload succeeded (norm: {norm:.9f})")
except Exception as e:
    print(f"✗ Unexpected error: {e}")
```

---

## Pre-Commit Checklist

Before committing your changes, verify:

### 1. Code Quality

```bash
cd functions/exr_inspector

# Run all tests
python -m pytest test_vast_db_persistence.py -v

# Check for syntax errors
python -m py_compile main.py vast_db_persistence.py

# Check imports
python -c "from main import handler; from vast_db_persistence import persist_to_vast_database; print('✓ Imports OK')"
```

Success criteria: All tests pass, no syntax errors, imports work.

### 2. Coverage Verification

```bash
python -m pytest test_vast_db_persistence.py --cov=vast_db_persistence --cov-report=term-missing --cov-fail-under=85
```

Success criteria: Coverage >= 85%

### 3. Test Edge Cases

```bash
# Run embedding tests specifically
python -m pytest test_vast_db_persistence.py::TestVectorEmbeddings -v

# Run error handling tests
python -m pytest test_vast_db_persistence.py::TestErrorHandling -v
```

Success criteria: All edge case tests pass.

### 4. Manual Verification

```bash
# Test with minimal payload
python3 << 'EOF'
from vast_db_persistence import compute_metadata_embedding
payload = {
    "file": {"multipart_count": 1, "is_deep": False},
    "channels": [],
    "parts": [],
}
embedding = compute_metadata_embedding(payload)
norm = sum(v * v for v in embedding) ** 0.5
assert abs(norm - 1.0) < 1e-5, f"Bad norm: {norm}"
print("✓ Manual verification passed")
EOF
```

Success criteria: Manual test passes without errors.

### 5. Git Status

```bash
git status
# Should show only modified source files

git diff functions/exr_inspector/main.py
# Review changes for logic errors

git diff functions/exr_inspector/vast_db_persistence.py
# Review changes for logic errors
```

Success criteria: Changes are intentional and well-understood.

### 6. Commit Message

```bash
git add functions/exr_inspector/

git commit -m "fix: correct vector embedding normalization in compute_metadata_embedding

- Fixed issue where L2 norm was slightly off due to floating point precision
- Added explicit normalization before output
- All 45 tests passing, coverage 92%

Closes #123"
```

Good commit messages:
- Start with conventional commit prefix (fix:, feat:, refactor:, test:, etc.)
- First line under 72 characters
- Explain the "why" not the "what"
- Reference related issues

### 7. Pre-Push Verification

```bash
# Verify tests one final time
python -m pytest test_vast_db_persistence.py -q

# Check git log
git log --oneline -5

# Verify branch
git branch -v

# Ready to push
git push origin feature/your-feature-name
```

---

## Common Development Tasks

### Adding a New Utility Function

```python
# In vast_db_persistence.py

def new_utility_function(input_data: Dict) -> Dict:
    """
    Brief description.

    Args:
        input_data: Description of input

    Returns:
        Description of output

    Raises:
        CustomError: When X happens

    Example:
        >>> result = new_utility_function({"key": "value"})
        >>> print(result)
    """
    # Implementation
    pass
```

Then add test in test_vast_db_persistence.py:

```python
class TestNewUtility(unittest.TestCase):
    def test_basic_case(self):
        result = new_utility_function({"key": "value"})
        self.assertEqual(result["expected_key"], "expected_value")

    def test_edge_case(self):
        result = new_utility_function({})
        # Verify behavior with minimal input
```

### Modifying Vector Embedding Logic

If changing embedding computation:

1. **Update both functions** (metadata embedding and channel fingerprint)
2. **Ensure determinism** - same input must always produce same output
3. **Check normalization** - L2 norm must be ~1.0
4. **Run embedding tests** - `pytest test_vast_db_persistence.py::TestVectorEmbeddings -v`
5. **Run persistence tests** - `pytest test_vast_db_persistence.py::TestPersistence -v`

### Updating Dependencies

```bash
# Add new dependency
pip install new-package-name
pip freeze > functions/exr_inspector/requirements.txt

# Test it works
python -m pytest test_vast_db_persistence.py -q

# Commit
git add functions/exr_inspector/requirements.txt
git commit -m "deps: add new-package-name for X feature"
```

---

## Troubleshooting Common Issues

### Issue: "ImportError: No module named 'OpenImageIO'"

**Solution:**
```bash
pip install -r functions/exr_inspector/requirements.txt
python -c "import OpenImageIO; print(OpenImageIO.__version__)"
```

### Issue: "Tests fail with 'AssertionError: 1.0234 != 1.0 (places=5)'"

**Likely cause:** Embedding normalization issue

**Debug:**
```python
from vast_db_persistence import compute_metadata_embedding
import math

payload = {...}
embedding = compute_metadata_embedding(payload)
norm = math.sqrt(sum(v * v for v in embedding))
print(f"Norm: {norm:.15f}")  # Should be very close to 1.0
```

### Issue: "TypeError: 'NoneType' object is not subscriptable"

**Solution:** Ensure payload has required keys:
```python
assert "file" in payload
assert "channels" in payload
assert "parts" in payload
```

### Issue: Virtual environment not activating

**Solution:**
```bash
# Deactivate any other envs
deactivate

# Recreate venv
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r functions/exr_inspector/requirements.txt
```

---

## Next Steps After Development

Once you've made changes and passed all checks:

1. **Push to feature branch:**
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create pull request** on GitHub with:
   - Clear description of changes
   - Link to any related issues
   - Test results summary

3. **Request review** from team members

4. **After approval, merge to main:**
   ```bash
   git checkout main
   git pull origin main
   git merge feature/your-feature-name
   git push origin main
   ```

5. **For production deployment**, see [PROD_RUNBOOK.md](PROD_RUNBOOK.md)

---

## References

- **Test file**: `functions/exr_inspector/test_vast_db_persistence.py` (45+ tests)
- **Vector strategy**: `docs/VECTOR_STRATEGY.md`
- **Troubleshooting**: `docs/TROUBLESHOOTING.md`
- **Production deployment**: `docs/PROD_RUNBOOK.md`

---

**Last Updated:** February 2025

**Version:** 0.9.0+

**Target Audience:** Developers performing local testing and iteration
