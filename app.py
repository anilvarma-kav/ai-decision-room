"""Hugging Face Spaces and local Gradio entry point."""

from decision_room.app import demo

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(server_name="0.0.0.0")
