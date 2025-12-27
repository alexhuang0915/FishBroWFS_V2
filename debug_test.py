#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from FishBroWFS_V2.control.lifecycle import PortOccupant, preflight_port
from unittest.mock import patch

# Create occupant similar to test
occupant = PortOccupant(
    occupied=True,
    pid=12345,
    cmdline='python -m FishBroWFS_V2.gui.nicegui.app'
)

print("Testing preflight_port with UI service type...")
with patch('FishBroWFS_V2.control.lifecycle.detect_port_occupant', return_value=occupant):
    with patch('FishBroWFS_V2.control.lifecycle.verify_fishbro_control_identity', return_value=(False, None, 'error')) as mock_control:
        with patch('FishBroWFS_V2.control.lifecycle.verify_fishbro_ui_identity', return_value=(True, None)) as mock_ui:
            result = preflight_port(8080, 'ui')
            print('Status:', result.status.value)
            print('Identity verified:', result.identity_verified)
            print('Identity error:', result.identity_error)
            print('Decision:', result.decision)
            print('mock_control called:', mock_control.called)
            print('mock_ui called:', mock_ui.called)
            print('mock_ui call args:', mock_ui.call_args if mock_ui.called else 'Not called')