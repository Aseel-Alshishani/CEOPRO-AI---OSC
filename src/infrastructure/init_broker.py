import redis

print(" Initializing CEOPRO AI Asynchronous Message Broker Topics...")
try:
    r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=3)
    topics = [
        "ceopro:stream:data_raw_uploaded",
        "ceopro:stream:demand_forecast_requested",
        "ceopro:stream:campaign_image_requested"
    ]
    for topic in topics:
        r.xadd(topic, {"status": "initialized"})
        print(f" [Broker Topic Live]: {topic}")
    print("\n All message broker queues are initialized and listening successfully!")
except Exception as e:
    print(f" [Broker Connection Failed] -> {e}")
