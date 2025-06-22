import redis
import json
from typing import Any, Callable, Dict, Optional
import threading

class RedisClient:
    def __init__(self):
        # Initialize Redis client
        self.redis = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        # Store the subscribers for each channel for cleanup
        self.pubsub_clients = {}
        self.callback_map = {}
        
    def publish(self, channel: str, message: Dict[str, Any]) -> int:
        """Publish a message to a Redis channel"""
        return self.redis.publish(channel, json.dumps(message))
    
    def subscribe(self, channel: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe to a Redis channel"""
        # Store the callback for this channel
        self.callback_map[channel] = callback
        
        # Create a new pubsub client
        pubsub = self.redis.pubsub()
        pubsub.subscribe(**{channel: self._message_handler})
        
        # Store the pubsub client for later cleanup
        self.pubsub_clients[channel] = pubsub
        
        # Start listening for messages in a separate thread
        thread = threading.Thread(target=pubsub.run_in_thread, kwargs={"sleep_time": 0.001})
        thread.daemon = True
        thread.start()
    
    def _message_handler(self, message):
        """Handle incoming Redis messages and route to the appropriate callback"""
        if message['type'] == 'message':
            channel = message['channel']
            data = json.loads(message['data'])
            if channel in self.callback_map:
                self.callback_map[channel](data)
    
    def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a Redis channel"""
        if channel in self.pubsub_clients:
            self.pubsub_clients[channel].unsubscribe(channel)
            self.pubsub_clients[channel].close()
            del self.pubsub_clients[channel]
            if channel in self.callback_map:
                del self.callback_map[channel]
            
    def add_to_set(self, set_name: str, value: str) -> int:
        """Add a value to a Redis set"""
        return self.redis.sadd(set_name, value)
    
    def remove_from_set(self, set_name: str, value: str) -> int:
        """Remove a value from a Redis set"""
        return self.redis.srem(set_name, value)
    
    def is_in_set(self, set_name: str, value: str) -> bool:
        """Check if a value is in a Redis set"""
        return self.redis.sismember(set_name, value)
    
    def get_set_members(self, set_name: str) -> list:
        """Get all members of a Redis set"""
        return self.redis.smembers(set_name)
    
    def increment(self, key: str, amount: int = 1) -> int:
        """Increment a value in Redis"""
        return self.redis.incrby(key, amount)
    
    def get_value(self, key: str) -> Optional[str]:
        """Get a value from Redis"""
        return self.redis.get(key)
    
    def set_value(self, key: str, value: str, expiration: Optional[int] = None) -> bool:
        """Set a value in Redis with optional expiration in seconds"""
        return self.redis.set(key, value, ex=expiration)
    
    def delete_key(self, key: str) -> int:
        """Delete a key from Redis"""
        return self.redis.delete(key)

# Create a singleton instance
redis_client = RedisClient()
