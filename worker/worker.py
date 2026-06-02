#!/usr/bin/env python3
"""
RabbitMQ Worker for Ray Tracer Rendering
Listens for render jobs and executes the C++ renderer with GLB scenes
"""

import pika
import json
import os
import subprocess
import logging
import time
from pathlib import Path
from datetime import datetime
import base64

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
RABBITMQ_URL = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/%2F')
QUEUE_NAME = os.getenv('RABBITMQ_QUEUE', 'render_jobs')
RENDERER_PATH = os.getenv('RENDERER_PATH', '/app/renderer/build/renderer')
SCENES_FOLDER = os.getenv('SCENES_FOLDER', '/tmp/scenes')
OUTPUT_FOLDER = os.getenv('OUTPUT_FOLDER', '/tmp/renders')
TEMP_FOLDER = os.getenv('TEMP_FOLDER', '/tmp')

# Ensure necessary directories exist
Path(SCENES_FOLDER).mkdir(parents=True, exist_ok=True)
Path(OUTPUT_FOLDER).mkdir(parents=True, exist_ok=True)


class RayTracerWorker:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.renderer_path = RENDERER_PATH
        
    def connect(self):
        """Establish connection to RabbitMQ"""
        try:
            logger.info(f"Connecting to RabbitMQ at {RABBITMQ_URL}")
            self.connection = pika.BlockingConnection(
                pika.URLParameters(RABBITMQ_URL)
            )
            self.channel = self.connection.channel()
            
            # Declare queue with durable flag
            self.channel.queue_declare(queue=QUEUE_NAME, durable=True)
            
            # Set QoS to ensure fair dispatch
            self.channel.basic_qos(prefetch_count=1)
            
            logger.info(f"Connected to RabbitMQ. Queue: {QUEUE_NAME}")
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise
    
    def save_glb_file(self, glb_data, scene_name):
        """
        Save GLB data to file
        
        Args:
            glb_data: Either base64 encoded string or file path
            scene_name: Name for the saved scene file
            
        Returns:
            Path to saved GLB file
        """
        scene_path = os.path.join(SCENES_FOLDER, f"{scene_name}.glb")
        
        try:
            if isinstance(glb_data, str):
                # Check if it's a file path or base64 encoded data
                if os.path.exists(glb_data):
                    logger.info(f"Using existing scene file: {glb_data}")
                    return glb_data
                else:
                    # Assume it's base64 encoded
                    logger.info(f"Decoding base64 GLB data for scene: {scene_name}")
                    glb_binary = base64.b64decode(glb_data)
                    with open(scene_path, 'wb') as f:
                        f.write(glb_binary)
            else:
                # Assume it's binary data
                logger.info(f"Writing binary GLB data for scene: {scene_name}")
                with open(scene_path, 'wb') as f:
                    f.write(glb_data)
            
            logger.info(f"Scene saved to: {scene_path}")
            return scene_path
        except Exception as e:
            logger.error(f"Error saving GLB file: {e}")
            raise
    
    def run_renderer(self, scene_path, output_path, job_params):
        """
        Execute the C++ renderer
        
        Args:
            scene_path: Path to GLB scene file
            output_path: Path where output PNG will be saved
            job_params: Dictionary with rendering parameters
                - samples: Number of samples (default: 30)
                - height: Image height in pixels (default: 520)
                - timeout: Timeout in seconds (default: 300)
        """
        try:
            # Extract parameters with defaults
            samples = job_params.get('samples', 30)
            height = job_params.get('height', 520)
            timeout = job_params.get('timeout', 300)
            
            # Build renderer command
            cmd = [
                self.renderer_path,
                '--scene', scene_path,
                '--output', output_path,
                '--samples', str(samples),
                '--height', str(height),
                '--headless'
            ]
            
            logger.info(f"Executing renderer: {' '.join(cmd)}")
            logger.info(f"Timeout: {timeout}s, Samples: {samples}, Height: {height}")
            
            # Run renderer with timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode != 0:
                logger.error(f"Renderer failed with return code {result.returncode}")
                logger.error(f"STDERR: {result.stderr}")
                raise RuntimeError(f"Renderer exited with code {result.returncode}")
            
            logger.info(f"Renderer output:\n{result.stdout}")
            
            # Verify output file was created
            if not os.path.exists(output_path):
                raise RuntimeError(f"Output file not created: {output_path}")
            
            file_size = os.path.getsize(output_path)
            logger.info(f"Render complete! Output: {output_path} ({file_size} bytes)")
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error(f"Renderer timed out after {timeout}s")
            raise
        except Exception as e:
            logger.error(f"Error running renderer: {e}")
            raise
    
    def load_output_file(self, output_path):
        """
        Load the rendered image file
        
        Args:
            output_path: Path to the PNG output file
            
        Returns:
            Base64 encoded PNG data
        """
        try:
            with open(output_path, 'rb') as f:
                image_data = f.read()
            return base64.b64encode(image_data).decode('utf-8')
        except Exception as e:
            logger.error(f"Error loading output file: {e}")
            raise
    
    def callback(self, ch, method, properties, body):
        """
        RabbitMQ message callback
        
        Expected message format:
        {
            "job_id": "unique_job_id",
            "scene_name": "scene_name",
            "scene_data": "base64_encoded_glb_or_file_path",
            "params": {
                "samples": 30,
                "height": 520,
                "timeout": 300
            }
        }
        """
        try:
            logger.info(f"Received job message, size: {len(body)} bytes")
            
            # Parse message
            message = json.loads(body.decode('utf-8'))
            job_id = message.get('job_id', f'job_{int(time.time())}')
            scene_name = message.get('scene_name', 'scene')
            scene_data = message.get('scene_data')
            params = message.get('params', {})
            
            logger.info(f"Processing job {job_id}: {scene_name}")
            
            if not scene_data:
                raise ValueError("Missing scene_data in message")
            
            # Save GLB file
            scene_path = self.save_glb_file(scene_data, f"{job_id}_{scene_name}")
            
            # Prepare output path
            output_path = os.path.join(
                OUTPUT_FOLDER, 
                f"{job_id}_{scene_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )
            
            # Run renderer
            self.run_renderer(scene_path, output_path, params)
            
            # Load output
            output_data = self.load_output_file(output_path)
            
            # Prepare response
            response = {
                "job_id": job_id,
                "status": "success",
                "output_path": output_path,
                "output_data": output_data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Send response back to reply_to queue if specified
            if properties.reply_to:
                logger.info(f"Sending response to {properties.reply_to}")
                self.channel.basic_publish(
                    exchange='',
                    routing_key=properties.reply_to,
                    body=json.dumps(response),
                    properties=pika.BasicProperties(
                        correlation_id=properties.correlation_id
                    )
                )
            
            # Acknowledge message
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(f"Job {job_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error processing job: {e}")
            
            # Send error response if reply_to is specified
            if properties.reply_to:
                error_response = {
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
                self.channel.basic_publish(
                    exchange='',
                    routing_key=properties.reply_to,
                    body=json.dumps(error_response),
                    properties=pika.BasicProperties(
                        correlation_id=properties.correlation_id
                    )
                )
            
            # Negative acknowledge to requeue
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def start_consuming(self):
        """Start consuming messages from the queue"""
        try:
            self.connect()
            
            logger.info(f"Starting to consume messages from queue: {QUEUE_NAME}")
            self.channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=self.callback
            )
            
            logger.info("Worker ready. Waiting for jobs...")
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            self.shutdown()
        except Exception as e:
            logger.error(f"Error in consumer: {e}")
            self.shutdown()
            raise
    
    def shutdown(self):
        """Gracefully shutdown the worker"""
        logger.info("Shutting down worker...")
        if self.channel and self.channel.is_open:
            self.channel.stop_consuming()
        if self.connection and self.connection.is_open:
            self.connection.close()
        logger.info("Worker shutdown complete")


def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("Ray Tracer Worker Started")
    logger.info(f"Renderer: {RENDERER_PATH}")
    logger.info(f"Scenes folder: {SCENES_FOLDER}")
    logger.info(f"Output folder: {OUTPUT_FOLDER}")
    logger.info("=" * 60)
    
    worker = RayTracerWorker()
    worker.start_consuming()


if __name__ == '__main__':
    main()
