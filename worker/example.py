#!/usr/bin/env python3
"""
Example usage of the ray tracer render job client
"""

from client import RenderJobClient


def example_1_simple_job():
    """Send a simple render job"""
    print("=" * 60)
    print("Example 1: Send a simple render job")
    print("=" * 60)
    
    client = RenderJobClient()
    client.send_render_job(
        glb_path='assets/Test.glb',
        samples=30,
        height=520,
        timeout=300
    )


def example_2_high_quality_job():
    """Send a high-quality render job"""
    print("=" * 60)
    print("Example 2: Send a high-quality render job")
    print("=" * 60)
    
    client = RenderJobClient()
    client.send_render_job(
        glb_path='assets/sponza/Sponza.glb',
        samples=100,
        height=1080,
        timeout=600  # Higher timeout for higher quality
    )


def example_3_with_response():
    """Send a job and wait for response"""
    print("=" * 60)
    print("Example 3: Send job and wait for response")
    print("=" * 60)
    
    client = RenderJobClient()
    client.send_render_job(
        glb_path='assets/Test.glb',
        output_queue='render_results',  # Will listen for response
        job_id='my_custom_job_001',
        samples=50,
        height=720,
        timeout=300
    )


def example_4_with_local_file():
    """Send a local GLB file"""
    print("=" * 60)
    print("Example 4: Send a local GLB file")
    print("=" * 60)
    
    client = RenderJobClient()
    client.send_render_job(
        glb_path='/path/to/your/scene.glb',  # Local file will be base64 encoded
        output_queue='render_results',
        samples=40,
        height=800
    )


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        example = sys.argv[1]
        if example == '1':
            example_1_simple_job()
        elif example == '2':
            example_2_high_quality_job()
        elif example == '3':
            example_3_with_response()
        elif example == '4':
            example_4_with_local_file()
        else:
            print(f"Unknown example: {example}")
            print("Usage: python3 example.py [1|2|3|4]")
            print("  1 - Simple render job")
            print("  2 - High-quality render job")
            print("  3 - Send job and wait for response")
            print("  4 - Send local GLB file")
    else:
        print("Ray Tracer Client Examples")
        print("=" * 60)
        print("Usage: python3 example.py [1|2|3|4]")
        print()
        print("1 - Simple render job")
        print("    Sends a quick render job with default parameters")
        print()
        print("2 - High-quality render job")
        print("    Sends a high-quality render with 100 samples at 1080p")
        print()
        print("3 - Send job and wait for response")
        print("    Sends a job and listens for the rendered result")
        print()
        print("4 - Send local GLB file")
        print("    Sends a local GLB file that will be base64 encoded")
        print()
        print("=" * 60)
