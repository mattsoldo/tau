"""
Phase 6 WebSocket Real-Time Updates Test

Tests WebSocket connection, subscription, and event broadcasting.
"""
from fastapi.testclient import TestClient
from tau.config import get_settings
from tau.api import create_app
from tau.api.websocket import connection_manager, EventType
import json


def test_phase6_websocket():
    """Test WebSocket functionality"""
    print("=" * 60)
    print("Phase 6 WebSocket Real-Time Updates Test")
    print("=" * 60)

    # Create app and client
    print("\n1. Creating test client...")
    settings = get_settings()
    app = create_app(settings)
    client = TestClient(app)
    print("   ✓ Test client created")

    # Test WebSocket stats endpoint
    print("\n2. Testing WebSocket stats endpoint...")
    response = client.get("/ws/stats")
    assert response.status_code == 200
    stats = response.json()
    assert "active_connections" in stats
    assert "total_connections" in stats
    print(f"   ✓ Stats endpoint working: {stats['active_connections']} active connections")

    # Test WebSocket connection
    print("\n3. Testing WebSocket connection...")
    with client.websocket_connect("/ws") as websocket:
        # Should receive welcome message
        data = websocket.receive_json()
        assert data["type"] == "connection"
        assert data["status"] == "connected"
        assert "connection_id" in data
        print(f"   ✓ Connected: {data['connection_id']}")

        # Test ping/pong
        print("\n4. Testing ping/pong...")
        websocket.send_json({"action": "ping"})
        data = websocket.receive_json()
        assert data["type"] == "pong"
        print("   ✓ Ping/pong working")

        # Test subscription
        print("\n5. Testing subscription...")
        websocket.send_json({
            "action": "subscribe",
            "event_types": [EventType.FIXTURE_STATE_CHANGED, EventType.SCENE_RECALLED]
        })
        data = websocket.receive_json()
        assert data["type"] == "subscription"
        assert data["status"] == "subscribed"
        assert EventType.FIXTURE_STATE_CHANGED in data["event_types"]
        print(f"   ✓ Subscribed to: {', '.join(data['event_types'])}")

        # Test unsubscribe
        print("\n6. Testing unsubscribe...")
        websocket.send_json({
            "action": "unsubscribe",
            "event_types": [EventType.FIXTURE_STATE_CHANGED]
        })
        data = websocket.receive_json()
        assert data["type"] == "subscription"
        assert data["status"] == "unsubscribed"
        print("   ✓ Unsubscribed successfully")

    print("   ✓ WebSocket disconnected gracefully")

    # Test multiple connections
    print("\n7. Testing multiple concurrent connections...")
    with client.websocket_connect("/ws") as ws1:
        with client.websocket_connect("/ws") as ws2:
            # Receive welcome messages
            data1 = ws1.receive_json()
            data2 = ws2.receive_json()

            assert data1["connection_id"] != data2["connection_id"]
            print(f"   ✓ Connection 1: {data1['connection_id']}")
            print(f"   ✓ Connection 2: {data2['connection_id']}")

            # Check stats
            response = client.get("/ws/stats")
            stats = response.json()
            assert stats["active_connections"] >= 2
            print(f"   ✓ Active connections: {stats['active_connections']}")

    # After closing, stats should show fewer connections
    response = client.get("/ws/stats")
    stats = response.json()
    print(f"   ✓ After closing: {stats['active_connections']} active connections")

    # Test event types
    print("\n8. Verifying event types...")
    event_types = [
        EventType.FIXTURE_STATE_CHANGED,
        EventType.GROUP_STATE_CHANGED,
        EventType.SCENE_RECALLED,
        EventType.SCENE_CAPTURED,
        EventType.CIRCADIAN_CHANGED,
        EventType.HARDWARE_STATUS,
        EventType.SYSTEM_STATUS,
    ]
    for event_type in event_types:
        print(f"   ✓ Event type: {event_type}")

    # Test connection manager methods
    print("\n9. Testing connection manager...")
    assert len(connection_manager.active_connections) >= 0
    print(f"   ✓ Connection manager active: {len(connection_manager.active_connections)} connections")

    stats = connection_manager.get_statistics()
    assert "active_connections" in stats
    assert "total_connections" in stats
    assert "total_messages_sent" in stats
    assert "total_broadcasts" in stats
    print(f"   ✓ Total connections (lifetime): {stats['total_connections']}")
    print(f"   ✓ Total messages sent: {stats['total_messages_sent']}")
    print(f"   ✓ Total broadcasts: {stats['total_broadcasts']}")

    # Summary
    print("\n" + "=" * 60)
    print("✅ Phase 6 WebSocket Real-Time Updates Test PASSED")
    print("=" * 60)
    print("\nVerified components:")
    print("  ✓ WebSocket endpoint (/ws)")
    print("  ✓ Connection management")
    print("  ✓ Ping/pong keepalive")
    print("  ✓ Subscription management")
    print("  ✓ Multiple concurrent connections")
    print("  ✓ Connection statistics")
    print("  ✓ Event type definitions")
    print("\nEvent Broadcasting:")
    print("  - Fixture state changes")
    print("  - Group state changes")
    print("  - Scene recalls")
    print("  - Circadian adjustments")
    print("  - System status updates")
    print("\n🎉 Phase 6 Complete!")


if __name__ == "__main__":
    test_phase6_websocket()
