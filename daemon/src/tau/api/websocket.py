"""
WebSocket Connection Manager and Event Broadcasting

Manages WebSocket connections and broadcasts state changes to connected clients.
"""
from typing import Dict, Set, List, Any
from fastapi import WebSocket
import structlog
import json
import asyncio
from datetime import datetime

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections and broadcasts events

    Tracks all active connections and provides methods to broadcast
    events to all connected clients or specific subsets.
    """

    def __init__(self):
        """Initialize connection manager"""
        # Active connections {connection_id: WebSocket}
        self.active_connections: Dict[str, WebSocket] = {}

        # Connection subscriptions {connection_id: Set[subscription_types]}
        self.subscriptions: Dict[str, Set[str]] = {}

        # Statistics
        self.total_connections = 0
        self.total_messages_sent = 0
        self.total_broadcasts = 0

        logger.info("websocket_connection_manager_initialized")

    async def connect(self, websocket: WebSocket, connection_id: str) -> None:
        """
        Accept and register a new WebSocket connection

        Args:
            websocket: WebSocket connection
            connection_id: Unique identifier for this connection
        """
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.subscriptions[connection_id] = set()  # Subscribe to all by default
        self.total_connections += 1

        logger.info(
            "websocket_connected",
            connection_id=connection_id,
            active_connections=len(self.active_connections)
        )

        # Send welcome message
        await self.send_personal_message(
            {
                "type": "connection",
                "status": "connected",
                "connection_id": connection_id,
                "timestamp": datetime.now().isoformat()
            },
            connection_id
        )

    def disconnect(self, connection_id: str) -> None:
        """
        Remove a connection

        Args:
            connection_id: Connection to remove
        """
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            del self.subscriptions[connection_id]

            logger.info(
                "websocket_disconnected",
                connection_id=connection_id,
                active_connections=len(self.active_connections)
            )

    async def send_personal_message(
        self,
        message: Dict[str, Any],
        connection_id: str
    ) -> bool:
        """
        Send message to a specific connection

        Args:
            message: Message dictionary to send
            connection_id: Target connection

        Returns:
            True if sent successfully, False otherwise
        """
        if connection_id not in self.active_connections:
            return False

        try:
            websocket = self.active_connections[connection_id]
            await websocket.send_json(message)
            self.total_messages_sent += 1
            return True
        except Exception as e:
            logger.error(
                "websocket_send_failed",
                connection_id=connection_id,
                error=str(e)
            )
            # Connection is broken, remove it
            self.disconnect(connection_id)
            return False

    async def broadcast(
        self,
        message: Dict[str, Any],
        event_type: str = None
    ) -> int:
        """
        Broadcast message to all connected clients

        Args:
            message: Message dictionary to broadcast
            event_type: Optional event type for subscription filtering

        Returns:
            Number of clients message was sent to
        """
        self.total_broadcasts += 1
        sent_count = 0

        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.now().isoformat()

        disconnected = []

        for connection_id, websocket in list(self.active_connections.items()):
            # Check if client is subscribed to this event type
            if event_type:
                subscriptions = self.subscriptions.get(connection_id, set())
                if subscriptions and event_type not in subscriptions:
                    continue  # Skip this client

            try:
                await websocket.send_json(message)
                sent_count += 1
                self.total_messages_sent += 1
            except Exception as e:
                logger.error(
                    "websocket_broadcast_failed",
                    connection_id=connection_id,
                    error=str(e)
                )
                disconnected.append(connection_id)

        # Clean up disconnected clients
        for connection_id in disconnected:
            self.disconnect(connection_id)

        logger.debug(
            "websocket_broadcast_sent",
            event_type=event_type or "all",
            sent_count=sent_count,
            active_connections=len(self.active_connections)
        )

        return sent_count

    def subscribe(self, connection_id: str, event_types: List[str]) -> bool:
        """
        Subscribe a connection to specific event types

        Args:
            connection_id: Connection to subscribe
            event_types: List of event types to subscribe to

        Returns:
            True if subscription successful
        """
        if connection_id not in self.subscriptions:
            return False

        self.subscriptions[connection_id].update(event_types)
        logger.debug(
            "websocket_subscribed",
            connection_id=connection_id,
            event_types=event_types
        )
        return True

    def unsubscribe(self, connection_id: str, event_types: List[str]) -> bool:
        """
        Unsubscribe a connection from specific event types

        Args:
            connection_id: Connection to unsubscribe
            event_types: List of event types to unsubscribe from

        Returns:
            True if unsubscription successful
        """
        if connection_id not in self.subscriptions:
            return False

        for event_type in event_types:
            self.subscriptions[connection_id].discard(event_type)

        logger.debug(
            "websocket_unsubscribed",
            connection_id=connection_id,
            event_types=event_types
        )
        return True

    def get_statistics(self) -> dict:
        """
        Get connection manager statistics

        Returns:
            Dictionary with statistics
        """
        return {
            "active_connections": len(self.active_connections),
            "total_connections": self.total_connections,
            "total_messages_sent": self.total_messages_sent,
            "total_broadcasts": self.total_broadcasts,
        }


# Global connection manager instance
connection_manager = ConnectionManager()


# Event types
class EventType:
    """Event type constants"""
    FIXTURE_STATE_CHANGED = "fixture_state_changed"
    GROUP_STATE_CHANGED = "group_state_changed"
    SCENE_RECALLED = "scene_recalled"
    SCENE_CAPTURED = "scene_captured"
    CIRCADIAN_CHANGED = "circadian_changed"
    HARDWARE_STATUS = "hardware_status"
    SYSTEM_STATUS = "system_status"


async def broadcast_fixture_state_change(
    fixture_id: int,
    brightness: float,
    color_temp: int | None = None
) -> None:
    """
    Broadcast fixture state change event

    Args:
        fixture_id: Fixture that changed
        brightness: New brightness (0.0-1.0) - values outside range are clamped
        color_temp: New color temperature in Kelvin (1000-10000) - values outside range are clamped

    Note:
        Invalid values are clamped to valid ranges and logged as warnings.
        This prevents broadcast failures from disrupting switch control.
    """
    # Validate brightness range
    if not 0.0 <= brightness <= 1.0:
        logger.warning(
            "invalid_brightness_value",
            fixture_id=fixture_id,
            brightness=brightness,
            clamped_to=max(0.0, min(1.0, brightness))
        )
        brightness = max(0.0, min(1.0, brightness))  # Clamp to valid range

    # Validate color temperature range (typical range: 1000K - 10000K)
    if color_temp is not None:
        if not 1000 <= color_temp <= 10000:
            logger.warning(
                "invalid_color_temp_value",
                fixture_id=fixture_id,
                color_temp=color_temp,
                clamped_to=max(1000, min(10000, color_temp))
            )
            color_temp = max(1000, min(10000, color_temp))  # Clamp to valid range

    message = {
        "type": EventType.FIXTURE_STATE_CHANGED,
        "fixture_id": fixture_id,
        "brightness": brightness,
        "color_temp": color_temp,
    }
    await connection_manager.broadcast(message, EventType.FIXTURE_STATE_CHANGED)


async def broadcast_group_state_change(
    group_id: int,
    brightness: float,
    color_temp: int | None = None
) -> None:
    """
    Broadcast group state change event

    Args:
        group_id: Group that changed
        brightness: New brightness (0.0-1.0) - values outside range are clamped
        color_temp: New color temperature in Kelvin (1000-10000) - values outside range are clamped

    Note:
        Invalid values are clamped to valid ranges and logged as warnings.
        This prevents broadcast failures from disrupting switch control.
    """
    # Validate brightness range
    if not 0.0 <= brightness <= 1.0:
        logger.warning(
            "invalid_brightness_value",
            group_id=group_id,
            brightness=brightness,
            clamped_to=max(0.0, min(1.0, brightness))
        )
        brightness = max(0.0, min(1.0, brightness))  # Clamp to valid range

    # Validate color temperature range (typical range: 1000K - 10000K)
    if color_temp is not None:
        if not 1000 <= color_temp <= 10000:
            logger.warning(
                "invalid_color_temp_value",
                group_id=group_id,
                color_temp=color_temp,
                clamped_to=max(1000, min(10000, color_temp))
            )
            color_temp = max(1000, min(10000, color_temp))  # Clamp to valid range

    message = {
        "type": EventType.GROUP_STATE_CHANGED,
        "group_id": group_id,
        "brightness": brightness,
        "color_temp": color_temp,
    }
    await connection_manager.broadcast(message, EventType.GROUP_STATE_CHANGED)


async def broadcast_scene_recalled(scene_id: int, scene_name: str) -> None:
    """
    Broadcast scene recalled event

    Args:
        scene_id: Scene that was recalled
        scene_name: Name of the scene
    """
    message = {
        "type": EventType.SCENE_RECALLED,
        "scene_id": scene_id,
        "scene_name": scene_name,
    }
    await connection_manager.broadcast(message, EventType.SCENE_RECALLED)


async def broadcast_circadian_change(
    group_id: int,
    enabled: bool,
    brightness: float = None,
    color_temp: int = None
) -> None:
    """
    Broadcast circadian state change event

    Args:
        group_id: Group affected
        enabled: Whether circadian is enabled
        brightness: Current circadian brightness
        color_temp: Current circadian CCT
    """
    message = {
        "type": EventType.CIRCADIAN_CHANGED,
        "group_id": group_id,
        "enabled": enabled,
        "brightness": brightness,
        "color_temp": color_temp,
    }
    await connection_manager.broadcast(message, EventType.CIRCADIAN_CHANGED)


async def broadcast_system_status(status_data: dict) -> None:
    """
    Broadcast system status update

    Args:
        status_data: Status information dictionary
    """
    message = {
        "type": EventType.SYSTEM_STATUS,
        "status": status_data,
    }
    await connection_manager.broadcast(message, EventType.SYSTEM_STATUS)
