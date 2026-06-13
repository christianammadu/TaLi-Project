"""Band SDK — multi-agent communication channel.
"""


class BandSDK:
    """Lightweight Event Broker for message-passing between agents."""

    _subscribers = {}

    @classmethod
    def subscribe(cls, channel, callback):
        """Subscribe an agent callback to a channel."""
        if channel not in cls._subscribers:
            cls._subscribers[channel] = []
        if callback not in cls._subscribers[channel]:
            cls._subscribers[channel].append(callback)

    @classmethod
    def publish(cls, channel, payload):
        """Publish a payload to a channel and collect return values."""
        results = []
        if channel in cls._subscribers:
            for callback in cls._subscribers[channel]:
                try:
                    res = callback(payload)
                    if res is not None:
                        results.append(res)
                except Exception as e:
                    print(f"[BandSDK Error] Callback failed on channel '{channel}': {e}")
        return results

    @classmethod
    def clear_subscriptions(cls):
        """Clear all active subscriptions to keep tests clean."""
        cls._subscribers = {}
