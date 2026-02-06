"""Unit tests for VAST DataBase persistence module.

Comprehensive tests covering:
- Vector embedding computation (determinism, normalization)
- PyArrow table conversion
- Path normalization
- Error handling
- Idempotent upsert logic (with mock session)
"""

import json
import math
import unittest
from unittest.mock import MagicMock, patch

try:
    import pyarrow as pa
except ImportError:
    pa = None

from vast_db_persistence import (
    compute_metadata_embedding,
    compute_channel_fingerprint,
    payload_to_files_row,
    payload_to_parts_rows,
    payload_to_channels_rows,
    payload_to_attributes_rows,
    persist_to_vast_database,
    VectorEmbeddingError,
    VASTDatabaseError,
    _normalize_path,
    _extract_metadata_features,
    _compression_to_normalized,
)


class TestVectorEmbeddings(unittest.TestCase):
    """Test vector embedding computation."""

    def test_metadata_embedding_determinism(self):
        """Same payload must produce identical vectors."""
        payload = {
            "file": {
                "path": "/data/test.exr",
                "multipart_count": 2,
                "is_deep": False,
            },
            "channels": [
                {"name": "R", "type": "float", "x_sampling": 1, "y_sampling": 1},
                {"name": "G", "type": "float", "x_sampling": 1, "y_sampling": 1},
            ],
            "parts": [
                {
                    "part_index": 0,
                    "compression": "zip",
                    "is_tiled": False,
                }
            ],
        }

        vec1 = compute_metadata_embedding(payload)
        vec2 = compute_metadata_embedding(payload)

        self.assertEqual(len(vec1), 384)
        self.assertEqual(len(vec2), 384)
        self.assertTrue(
            all(abs(v1 - v2) < 1e-9 for v1, v2 in zip(vec1, vec2))
        )

    def test_metadata_embedding_unit_norm(self):
        """Output vector must be normalized (unit vector)."""
        payload = {
            "file": {"multipart_count": 1, "is_deep": False},
            "channels": [],
            "parts": [{"compression": "none"}],
        }

        vec = compute_metadata_embedding(payload)
        norm = (sum(v * v for v in vec) ** 0.5)

        # L2 norm should be approximately 1.0
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_metadata_embedding_dimension(self):
        """Output dimension must match requested size."""
        payload = {
            "file": {"multipart_count": 1},
            "channels": [],
            "parts": [],
        }

        for dim in [64, 128, 256, 384, 512]:
            vec = compute_metadata_embedding(payload, embedding_dim=dim)
            self.assertEqual(len(vec), dim)

    def test_metadata_embedding_different_payloads(self):
        """Different payloads should produce different vectors."""
        payload1 = {
            "file": {"multipart_count": 1, "is_deep": False},
            "channels": [],
            "parts": [{"compression": "none"}],
        }
        payload2 = {
            "file": {"multipart_count": 2, "is_deep": True},
            "channels": [],
            "parts": [{"compression": "zip"}],
        }

        vec1 = compute_metadata_embedding(payload1)
        vec2 = compute_metadata_embedding(payload2)

        # Vectors should be different (not identical)
        differences = [abs(v1 - v2) for v1, v2 in zip(vec1, vec2)]
        self.assertTrue(max(differences) > 0.01)

    def test_metadata_embedding_invalid_payload(self):
        """Invalid payload should raise VectorEmbeddingError."""
        invalid_payloads = [
            None,
            "not a dict",
            {},  # Missing file key
            {"file": None},  # Invalid file value
        ]

        for payload in invalid_payloads:
            with self.assertRaises(VectorEmbeddingError):
                compute_metadata_embedding(payload)

    def test_channel_fingerprint_determinism(self):
        """Same channels must produce identical fingerprints."""
        channels = [
            {"name": "R", "type": "float", "x_sampling": 1, "y_sampling": 1},
            {"name": "G", "type": "float", "x_sampling": 1, "y_sampling": 1},
            {"name": "B", "type": "float", "x_sampling": 1, "y_sampling": 1},
        ]

        fp1 = compute_channel_fingerprint(channels)
        fp2 = compute_channel_fingerprint(channels)

        self.assertEqual(len(fp1), 128)
        self.assertTrue(all(abs(v1 - v2) < 1e-9 for v1, v2 in zip(fp1, fp2)))

    def test_channel_fingerprint_unit_norm(self):
        """Fingerprint must be normalized."""
        channels = [{"name": "R", "type": "float"}]
        fp = compute_channel_fingerprint(channels)
        norm = (sum(v * v for v in fp) ** 0.5)
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_channel_fingerprint_empty(self):
        """Empty channel list should produce valid vector."""
        fp = compute_channel_fingerprint([])
        self.assertEqual(len(fp), 128)
        self.assertTrue(all(v == 0.0 for v in fp))

    def test_channel_fingerprint_different_channels(self):
        """Different channel configs should produce different fingerprints."""
        channels1 = [
            {"name": "R", "type": "float", "x_sampling": 1, "y_sampling": 1},
        ]
        channels2 = [
            {"name": "R", "type": "half", "x_sampling": 2, "y_sampling": 2},
            {"name": "G", "type": "float", "x_sampling": 1, "y_sampling": 1},
        ]

        fp1 = compute_channel_fingerprint(channels1)
        fp2 = compute_channel_fingerprint(channels2)

        differences = [abs(v1 - v2) for v1, v2 in zip(fp1, fp2)]
        self.assertTrue(max(differences) > 0.01)


class TestPathNormalization(unittest.TestCase):
    """Test path normalization."""

    def test_normalize_path_basic(self):
        """Basic path normalization."""
        path = "/data/test.exr"
        normalized = _normalize_path(path)

        # Should be lowercase and forward slashes
        self.assertTrue(normalized.islower() or "/" in normalized)
        self.assertNotIn("\\", normalized)

    def test_normalize_path_consistency(self):
        """Same path should normalize consistently."""
        path = "/Data/Test.EXR"
        norm1 = _normalize_path(path)
        norm2 = _normalize_path(path)

        self.assertEqual(norm1, norm2)

    def test_normalize_path_mixed_separators(self):
        """Mixed separators should be normalized."""
        # This tests behavior on current platform
        paths = ["/data/test.exr", "data/test.exr"]
        for path in paths:
            normalized = _normalize_path(path)
            self.assertNotIn("\\", normalized)


class TestMetadataFeatureExtraction(unittest.TestCase):
    """Test feature extraction from payload."""

    def test_extract_features_complete(self):
        """Extract all features from complete payload."""
        payload = {
            "file": {"multipart_count": 2, "is_deep": True},
            "channels": [
                {"name": "R", "type": "float"},
                {"name": "G", "type": "float"},
            ],
            "parts": [
                {"compression": "zip", "is_tiled": True, "multi_view": True},
                {"compression": "piz", "is_tiled": False},
            ],
        }

        features = _extract_metadata_features(payload)

        self.assertEqual(features["channel_count"], 2)
        self.assertEqual(features["part_count"], 2)
        self.assertTrue(features["is_deep"])
        self.assertTrue(features["is_tiled"])
        self.assertTrue(features["has_multiview"])

    def test_extract_features_minimal(self):
        """Extract features from minimal payload."""
        payload = {"file": {}, "channels": [], "parts": []}
        features = _extract_metadata_features(payload)

        self.assertEqual(features["channel_count"], 0)
        self.assertEqual(features["part_count"], 0)
        self.assertFalse(features["is_deep"])
        self.assertFalse(features["is_tiled"])


class TestCompressionNormalization(unittest.TestCase):
    """Test compression type normalization."""

    def test_compression_to_normalized_known(self):
        """Known compressions should map consistently."""
        compressions = {
            "none": 0.0,
            "rle": 0.2,
            "zip": 0.5,
            "piz": 0.6,
        }

        for comp, expected_val in compressions.items():
            val = _compression_to_normalized(comp)
            self.assertAlmostEqual(val, expected_val, places=1)

    def test_compression_to_normalized_case_insensitive(self):
        """Compression normalization should be case-insensitive."""
        val_lower = _compression_to_normalized("zip")
        val_upper = _compression_to_normalized("ZIP")
        val_mixed = _compression_to_normalized("Zip")

        self.assertEqual(val_lower, val_upper)
        self.assertEqual(val_lower, val_mixed)

    def test_compression_to_normalized_unknown(self):
        """Unknown compression should map to fallback."""
        val = _compression_to_normalized("unknown_compression")
        self.assertGreater(val, 0.0)
        self.assertLess(val, 1.0)


@unittest.skipIf(pa is None, "pyarrow not installed")
class TestPyArrowConversion(unittest.TestCase):
    """Test PyArrow table conversion."""

    def test_payload_to_files_row_basic(self):
        """Convert payload to files row."""
        payload = {
            "file": {
                "path": "/data/test.exr",
                "size_bytes": 1024000,
                "mtime": "2025-02-05T10:00:00+00:00",
                "multipart_count": 1,
                "is_deep": False,
            },
            "channels": [],
            "parts": [],
        }
        embedding = [0.1] * 384

        table = payload_to_files_row(payload, embedding)

        self.assertIsNotNone(table)
        self.assertEqual(table.num_rows, 1)
        self.assertIn("file_id", table.column_names)
        self.assertIn("metadata_embedding", table.column_names)

    def test_payload_to_files_row_missing_path(self):
        """Should raise ValueError if path is missing."""
        payload = {
            "file": {"size_bytes": 1024},
            "channels": [],
            "parts": [],
        }
        embedding = [0.1] * 384

        with self.assertRaises(ValueError):
            payload_to_files_row(payload, embedding)

    def test_payload_to_parts_rows_multiple(self):
        """Convert multiple parts to rows."""
        payload = {
            "file": {"path": "/data/test.exr"},
            "channels": [],
            "parts": [
                {"part_index": 0, "compression": "zip"},
                {"part_index": 1, "compression": "piz"},
            ],
        }

        table = payload_to_parts_rows(payload, "file_id_1")

        self.assertEqual(table.num_rows, 2)
        self.assertIn("part_index", table.column_names)

    def test_payload_to_parts_rows_empty(self):
        """Empty parts should produce empty table."""
        payload = {
            "file": {"path": "/data/test.exr"},
            "channels": [],
            "parts": [],
        }

        table = payload_to_parts_rows(payload, "file_id_1")

        self.assertEqual(table.num_rows, 0)

    def test_payload_to_channels_rows_multiple(self):
        """Convert multiple channels to rows."""
        payload = {
            "file": {"path": "/data/test.exr"},
            "channels": [
                {"name": "R", "type": "float", "x_sampling": 1, "y_sampling": 1},
                {"name": "G", "type": "float", "x_sampling": 1, "y_sampling": 1},
            ],
            "parts": [],
        }
        fingerprint = [0.1] * 128

        table = payload_to_channels_rows(payload, "file_id_1", fingerprint)

        self.assertEqual(table.num_rows, 2)
        self.assertIn("channel_name", table.column_names)

    def test_payload_to_attributes_rows_multiple(self):
        """Convert multiple attributes to rows."""
        payload = {
            "file": {"path": "/data/test.exr"},
            "channels": [],
            "parts": [],
            "attributes": {
                "parts": [
                    [
                        {"name": "cameraName", "type": "string", "value": "cam1"},
                    ],
                    [
                        {"name": "comment", "type": "string", "value": "test"},
                    ],
                ]
            },
        }

        table = payload_to_attributes_rows(payload, "file_id_1")

        self.assertEqual(table.num_rows, 2)
        self.assertIn("attribute_name", table.column_names)


class TestPersistenceWithMockSession(unittest.TestCase):
    """Test persistence logic with mock VAST session."""

    def setUp(self):
        """Set up mock session."""
        self.mock_session = MagicMock()
        self.mock_txn = MagicMock()
        self.mock_table_client = MagicMock()

        self.mock_session.begin.return_value = self.mock_txn
        self.mock_session.table.return_value = self.mock_table_client
        self.mock_table_client.select.return_value = None  # No existing file
        self.mock_table_client.insert.return_value = None

    def test_persist_new_file_success(self):
        """Successful persistence of new file."""
        payload = {
            "file": {
                "path": "/data/test.exr",
                "size_bytes": 1024000,
                "mtime": "2025-02-05T10:00:00+00:00",
                "multipart_count": 1,
                "is_deep": False,
            },
            "channels": [
                {"name": "R", "type": "float", "x_sampling": 1, "y_sampling": 1},
            ],
            "parts": [{"part_index": 0, "compression": "zip"}],
            "attributes": {"parts": [[]]},
        }

        result = persist_to_vast_database(payload, {}, self.mock_session)

        self.assertEqual(result["status"], "success")
        self.assertIsNotNone(result["file_id"])
        self.assertTrue(result["inserted"])
        self.mock_txn.commit.assert_called()

    def test_persist_existing_file_idempotent(self):
        """Idempotent behavior for existing file."""
        payload = {
            "file": {
                "path": "/data/test.exr",
                "size_bytes": 1024000,
                "mtime": "2025-02-05T10:00:00+00:00",
                "multipart_count": 1,
                "is_deep": False,
            },
            "channels": [],
            "parts": [],
            "attributes": {"parts": [[]]},
        }

        # Mock returns existing file
        self.mock_table_client.select.return_value = [
            {"file_id": "existing_id_123"}
        ]

        result = persist_to_vast_database(payload, {}, self.mock_session)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["file_id"], "existing_id_123")
        self.assertFalse(result["inserted"])

    def test_persist_transaction_rollback_on_error(self):
        """Transaction rollback on error."""
        payload = {
            "file": {
                "path": "/data/test.exr",
                "size_bytes": 1024000,
                "mtime": "2025-02-05T10:00:00+00:00",
                "multipart_count": 1,
                "is_deep": False,
            },
            "channels": [],
            "parts": [],
            "attributes": {"parts": [[]]},
        }

        # Mock insert to raise error
        self.mock_table_client.insert.side_effect = Exception("Insert failed")

        result = persist_to_vast_database(payload, {}, self.mock_session)

        self.assertEqual(result["status"], "error")
        self.mock_txn.rollback.assert_called()

    def test_persist_missing_file_path(self):
        """Error if file path is missing."""
        payload = {
            "file": {"size_bytes": 1024},
            "channels": [],
            "parts": [],
        }

        result = persist_to_vast_database(payload, {}, self.mock_session)

        self.assertEqual(result["status"], "error")
        self.assertIn("file.path", result["error"])

    def test_persist_no_session_not_configured(self):
        """Skip persistence if VAST not configured."""
        payload = {
            "file": {
                "path": "/data/test.exr",
                "size_bytes": 1024000,
            },
            "channels": [],
            "parts": [],
        }

        # Don't provide session, don't set env vars
        with patch.dict("os.environ", clear=True):
            result = persist_to_vast_database(payload, {})

        self.assertEqual(result["status"], "skipped")


class TestErrorHandling(unittest.TestCase):
    """Test error handling."""

    def test_vector_embedding_error_invalid_payload(self):
        """VectorEmbeddingError on invalid payload."""
        with self.assertRaises(VectorEmbeddingError):
            compute_metadata_embedding(None)

    def test_persist_embedding_error_propagates(self):
        """Embedding error should be caught and returned."""
        payload = {
            "file": {"path": "/data/test.exr"},
            "channels": None,  # Invalid
            "parts": [],
        }

        mock_session = MagicMock()
        result = persist_to_vast_database(payload, {}, mock_session)

        self.assertEqual(result["status"], "error")
        self.assertIn("embedding", result["message"].lower())


class TestIntegrationScenarios(unittest.TestCase):
    """Integration test scenarios."""

    def test_full_workflow_multipart_exr(self):
        """Full workflow: multipart EXR with multiple channels."""
        payload = {
            "schema_version": 1,
            "file": {
                "path": "/renders/shot_001_beauty.exr",
                "size_bytes": 5242880,
                "mtime": "2025-02-05T15:30:00+00:00",
                "multipart_count": 3,
                "is_deep": False,
            },
            "parts": [
                {
                    "part_index": 0,
                    "part_name": "beauty",
                    "compression": "piz",
                    "is_tiled": True,
                    "tile_width": 64,
                    "tile_height": 64,
                    "is_deep": False,
                },
                {
                    "part_index": 1,
                    "part_name": "diffuse",
                    "compression": "piz",
                    "is_tiled": True,
                    "is_deep": False,
                },
                {
                    "part_index": 2,
                    "part_name": "deep",
                    "compression": "zip",
                    "is_deep": True,
                },
            ],
            "channels": [
                # Beauty part
                {"name": "R", "part_index": 0, "type": "float", "x_sampling": 1, "y_sampling": 1},
                {"name": "G", "part_index": 0, "type": "float", "x_sampling": 1, "y_sampling": 1},
                {"name": "B", "part_index": 0, "type": "float", "x_sampling": 1, "y_sampling": 1},
                {"name": "A", "part_index": 0, "type": "float", "x_sampling": 1, "y_sampling": 1},
                # Diffuse part
                {"name": "R", "part_index": 1, "type": "half", "x_sampling": 1, "y_sampling": 1},
                {"name": "G", "part_index": 1, "type": "half", "x_sampling": 1, "y_sampling": 1},
                {"name": "B", "part_index": 1, "type": "half", "x_sampling": 1, "y_sampling": 1},
            ],
            "attributes": {
                "parts": [
                    [
                        {"name": "cameraName", "type": "string", "value": "camera_001"},
                    ],
                    [
                        {"name": "renderTime", "type": "float", "value": 3600.5},
                    ],
                    [],
                ]
            },
            "errors": [],
        }

        # Test embedding computation
        metadata_emb = compute_metadata_embedding(payload)
        channel_fp = compute_channel_fingerprint(payload.get("channels", []))

        self.assertEqual(len(metadata_emb), 384)
        self.assertEqual(len(channel_fp), 128)

        # Verify embeddings are normalized
        metadata_norm = sum(v * v for v in metadata_emb) ** 0.5
        channel_norm = sum(v * v for v in channel_fp) ** 0.5

        self.assertAlmostEqual(metadata_norm, 1.0, places=5)
        self.assertAlmostEqual(channel_norm, 1.0, places=5)

    def test_full_workflow_with_mock_session(self):
        """Full workflow with mock VAST session."""
        payload = {
            "file": {
                "path": "/data/complex.exr",
                "size_bytes": 10485760,
                "mtime": "2025-02-05T14:20:00+00:00",
                "multipart_count": 2,
                "is_deep": True,
            },
            "channels": [
                {"name": "R", "type": "float", "x_sampling": 1, "y_sampling": 1},
                {"name": "G", "type": "float", "x_sampling": 1, "y_sampling": 1},
                {"name": "Z", "type": "float", "x_sampling": 1, "y_sampling": 1},
            ],
            "parts": [
                {"part_index": 0, "compression": "dwab", "is_tiled": False},
                {"part_index": 1, "compression": "pxr24", "is_tiled": True},
            ],
            "attributes": {"parts": [[]]},
        }

        mock_session = MagicMock()
        mock_txn = MagicMock()
        mock_table_client = MagicMock()

        mock_session.begin.return_value = mock_txn
        mock_session.table.return_value = mock_table_client
        mock_table_client.select.return_value = None

        result = persist_to_vast_database(payload, {}, mock_session)

        self.assertEqual(result["status"], "success")
        self.assertIsNotNone(result["file_id"])
        self.assertTrue(result["inserted"])


if __name__ == "__main__":
    unittest.main()
