#!/usr/bin/env python3
"""
RabbitMQ Client for sending render jobs to the ray tracer worker
"""

import pika
import json
import base64
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime


class RenderJobClient:
    def __init__(self, rabbitmq_url='amqp://guest:guest@localhost:5672/%2F'):
        self.rabbitmq_url = rabbitmq_url
        self.connection = None
        self.channel = None
    
    def connect(self):
        """Connect to RabbitMQ"""
        try:
            self.connection = pika.BlockingConnection(
                pika.URLParameters(self.rabbitmq_url)
            )
            self.channel = self.connection.channel()
            print(f"Connected to RabbitMQ at {self.rabbitmq_url}")
        except Exception as e:
            print(f"Failed to connect to RabbitMQ: {e}")
            sys.exit(1)
    
    def read_glb_file(self, file_path):
        """Read GLB file and encode as base64"""
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            return base64.b64encode(data).decode('utf-8')
        except Exception as e:
            print(f"Error reading GLB file: {e}")
            sys.exit(1)
    
    def send_render_job(self, glb_path, output_queue=None, job_id=None, 
                       samples=30, height=520, timeout=300):
        """
        Send a render job to the worker
        
        Args:
            glb_path: Path to GLB file or URL
            output_queue: Queue name for response (optional)
            job_id: Unique job ID (auto-generated if not provided)
            samples: Number of samples per pixel
            height: Output image height
            timeout: Render timeout in seconds
        """
        self.connect()
        
        try:
            # Generate job ID if not provided
            if not job_id:
                job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            
            # Check if it's a file or path
            if os.path.exists(glb_path):
                print(f"Reading GLB file: {glb_path}")
                scene_data = self.read_glb_file(glb_path)
                scene_name = Path(glb_path).stem
            else:
                # Assume it's a path within the renderer (like assets/Test.glb)
                print(f"Using scene path: {glb_path}")
                scene_data = glb_path
                scene_name = Path(glb_path).stem
            
            # Prepare render job message
            render_job = {
                "job_id": job_id,
                "scene_name": scene_name,
                "scene_data": scene_data,
                "params": {
                    "samples": samples,
                    "height": height,
                    "timeout": timeout
                }
            }
            
            # Prepare message properties
            properties = pika.BasicProperties(
                delivery_mode=pika.spec.PERSISTENT_MODE,
                correlation_id=job_id
            )
            
            if output_queue:
                properties.reply_to = output_queue
            
            # Send message
            self.channel.basic_publish(
                exchange='',
                routing_key='render_jobs',
                body=json.dumps(render_job),
                properties=properties
            )
            
            print(f"\nRender job sent successfully!")
            print(f"  Job ID: {job_id}")
            print(f"  Scene: {scene_name}")
            print(f"  Samples: {samples}")
            print(f"  Height: {height}px")
            print(f"  Timeout: {timeout}s")
            
            if output_queue:
                print(f"  Response queue: {output_queue}")
                print(f"\nListening for response on '{output_queue}'...")
                self.listen_for_response(output_queue, job_id)
            
            self.close()
            
        except Exception as e:
            print(f"Error sending render job: {e}")
            sys.exit(1)
    
    def listen_for_response(self, queue_name, correlation_id, timeout=3600):
        """
        Listen for render job response
        
        Args:
            queue_name: Queue to listen on
            correlation_id: Job ID to match
            timeout: Timeout in seconds
        """
        try:
            # Declare response queue
            self.channel.queue_declare(queue=queue_name, durable=False)
            
            # Define callback
            def on_response(ch, method, props, body):
                if props.correlation_id == correlation_id:
                    response = json.loads(body.decode('utf-8'))
                    
                    if response.get('status') == 'success':
                        print(f"\n✓ Render completed successfully!")
                        print(f"  Output: {response.get('output_path')}")
                        
                        # Save base64 image
                        output_data = response.get('output_data')
                        if output_data:
                            filename = f"render_{correlation_id}.png"
                            with open(filename, 'wb') as f:
                                f.write(base64.b64decode(output_data))
                            print(f"  Saved to: {filename}")
                    else:
                        print(f"\n✗ Render failed!")
                        print(f"  Error: {response.get('error')}")
                    
                    ch.stop_consuming()
            
            # Set up listener
            self.channel.basic_consume(
                queue=queue_name,
                on_message_callback=on_response,
                auto_ack=True
            )
            
            print(f"Waiting for response (timeout: {timeout}s)...")
            self.channel.start_consuming()
            
        except Exception as e:
            print(f"Error listening for response: {e}")
    
    def close(self):
        """Close RabbitMQ connection"""
        if self.connection and self.connection.is_open:
            self.connection.close()


def main():
    parser = argparse.ArgumentParser(
        description='Send a render job to the ray tracer worker'
    )
    parser.add_argument('glb_file', help='Path to GLB scene file')
    parser.add_argument('--job-id', help='Unique job ID (auto-generated if not provided)')
    parser.add_argument('--samples', type=int, default=30,
                       help='Number of samples per pixel (default: 30)')
    parser.add_argument('--height', type=int, default=520,
                       help='Output image height in pixels (default: 520)')
    parser.add_argument('--timeout', type=int, default=300,
                       help='Render timeout in seconds (default: 300)')
    parser.add_argument('--wait', action='store_true',
                       help='Wait for render result')
    parser.add_argument('--rabbitmq-url',
                       default='amqp://guest:guest@localhost:5672/%2F',
                       help='RabbitMQ URL (default: amqp://guest:guest@localhost:5672/%%2F)')
    
    args = parser.parse_args()
    
    client = RenderJobClient(args.rabbitmq_url)
    
    # Prepare response queue if waiting
    output_queue = 'render_results' if args.wait else None
    
    client.send_render_job(
        glb_path=args.glb_file,
        output_queue=output_queue,
        job_id=args.job_id,
        samples=args.samples,
        height=args.height,
        timeout=args.timeout
    )


if __name__ == '__main__':
    main()
