import pytest
from pathlib import Path
from unittest.mock import patch
from gui.desktop.services.evidence_locator import EvidenceLocator, EvidenceLookupError, get_evidence_root, list_evidence_files

def test_get_evidence_root_raises_not_found():
    """L3-1: Verify get_evidence_root raises EvidenceLookupError when path not found."""
    with patch("gui.desktop.services.evidence_locator.get_reveal_evidence_path") as mock_reveal:
        mock_reveal.return_value = {"path": "/non/existent/path"}
        
        with pytest.raises(EvidenceLookupError, match="Evidence path does not exist"):
            get_evidence_root("fake_job")

def test_get_evidence_root_raises_error_response():
    """L3-1: Verify get_evidence_root raises on API error."""
    with patch("gui.desktop.services.evidence_locator.get_reveal_evidence_path") as mock_reveal:
        mock_reveal.return_value = {"error": "Internal Error"}
        
        with pytest.raises(EvidenceLookupError, match="Supervisor returned invalid evidence path"):
            get_evidence_root("fake_job")

def test_list_evidence_files_propagates_error():
    """L3-1: Verify list_evidence_files propagates exception."""
    with patch("gui.desktop.services.evidence_locator.EvidenceLocator.get_evidence_root") as mock_root:
        mock_root.side_effect = EvidenceLookupError("Root missing")
        
        with pytest.raises(EvidenceLookupError, match="Root missing"):
            list_evidence_files("fake_job")
