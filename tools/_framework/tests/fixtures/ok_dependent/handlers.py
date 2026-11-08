RECEIVED: list = []


def on_ping(**payload):
    RECEIVED.append(payload)
