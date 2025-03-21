#!/usr/bin/env python3
import os
import sys
import json
import argparse
from datetime import datetime
import requests
from PIL import Image, ImageDraw, ImageFont
import io
import base64
import time
from typing import Dict, Tuple

class ImageProcessor:
    def __init__(self, max_dimension=896):
        self.max_dimension = max_dimension
        
    def process_image(self, file_path, quality=100, scale_factor=1.0):
        try:
            # Create output directory if it doesn't exist
            output_dir = os.path.dirname(file_path)
            os.makedirs(output_dir, exist_ok=True)
            
            # Load the image
            img = Image.open(file_path)
            
            # Calculate the effective max dimension based on scale factor
            effective_max_dimension = int(self.max_dimension * scale_factor)
            
            # Constrain to effective max dimension while preserving aspect ratio
            width, height = img.size
            if width > effective_max_dimension or height > effective_max_dimension:
                if width > height:
                    new_height = int(height * (effective_max_dimension / width))
                    new_width = effective_max_dimension
                else:
                    new_width = int(width * (effective_max_dimension / height))
                    new_height = effective_max_dimension
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert to RGB if needed (for PNG with transparency)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
                img = background
            
            # Save to buffer with specified quality
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality)
            buffer.seek(0)
            
            # Convert to base64
            img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            
            # Create output path (not actually saving the file here)
            filename = os.path.basename(file_path)
            name, _ = os.path.splitext(filename)
            output_path = os.path.join(output_dir, f"{name}_q{quality}_s{int(scale_factor*100)}.jpg")
            
            return img_base64, output_path
            
        except Exception as e:
            print(f"Error processing image {file_path}: {str(e)}")
            return None, None

class LLMProcessor:
    def __init__(self, api_url, api_password):
        self.max_length = 1024
        self.top_p = 1
        self.top_k = 0
        self.temperature = 0.1
        self.rep_pen = 1
        self.min_p = 0.1
        self.api_url = api_url
        self.api_password = api_password
        self.image_processor = ImageProcessor(max_dimension=896)
        self.system_instruction = "You are a helpful image capable model"
        self.instruction = "Describe the image. Make sure to list every object that can be recognized and the location of that object. If there is any writing, transcribe it separately."
        
    def process_file(self, file_path, quality=100, scale_factor=1.0):
        start_time = time.time()
        image_base64, output_path = self.image_processor.process_image(
            file_path, 
            quality=quality,
            scale_factor=scale_factor
        )
        
        if not image_base64:
            return {
                "success": False,
                "error": "Failed to process image",
                "file_path": file_path,
                "quality": quality,
                "scale_factor": scale_factor,
                "timestamp": datetime.now().isoformat()
            }
            
        user_content = [{"type": "text", "text": self.instruction}]
        
        if image_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }
            })
            
        try:
            messages = [
                {"role": "system", "content": self.system_instruction},
                {
                    "role": "user", 
                    "content": user_content 
                }
            ]
            
            payload = {
                "messages": messages,
                "max_tokens": self.max_length,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "top_k": self.top_k,
                "rep_pen": self.rep_pen,
                "min_p": self.min_p
            }
            
            endpoint = f"{self.api_url}/v1/chat/completions"
            
            headers = {
                "Content-Type": "application/json"
            }
            
            if self.api_password:
                headers["Authorization"] = f"Bearer {self.api_password}"
            
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers
            )
            
            response.raise_for_status()
            response_json = response.json()
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            result = {
                "success": True,
                "file_path": file_path,
                "output_path": output_path,
                "quality": quality,
                "scale_factor": scale_factor,
                "timestamp": datetime.now().isoformat(),
                "processing_time": processing_time,
                "payload": payload,
                "response": None
            }
            
            if "choices" in response_json and len(response_json["choices"]) > 0:
                if "message" in response_json["choices"][0]:
                    result["response"] = response_json["choices"][0]["message"]["content"]
                else:
                    result["response"] = response_json["choices"][0].get("text", "")
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "file_path": file_path,
                "quality": quality,
                "scale_factor": scale_factor,
                "timestamp": datetime.now().isoformat()
            }

def create_side_by_side_image(original_path, result, output_dir):
    try:
        # Load the original image
        original_img = Image.open(original_path)
        
        # Get the processing parameters
        scale_factor = result.get("scale_factor", 1.0)
        quality = result.get("quality", 100)
        
        # Calculate the effective max dimension for display
        max_dimension = 896  # This is the baseline max dimension
        effective_max_dimension = int(max_dimension * scale_factor)
        
        # For display purposes, resize based on the effective dimension
        width, height = original_img.size
        if width > height:
            if width > effective_max_dimension:
                display_height = int(height * (effective_max_dimension / width))
                display_width = effective_max_dimension
            else:
                display_width, display_height = width, height
        else:
            if height > effective_max_dimension:
                display_width = int(width * (effective_max_dimension / height))
                display_height = effective_max_dimension
            else:
                display_width, display_height = width, height
        
        # Resize for display
        display_img = original_img.resize((display_width, display_height), Image.Resampling.LANCZOS)
        
        # Create a new image with text on the right
        font_size = 14
        font = ImageFont.load_default()
        
        # Calculate dimensions
        img_width, img_height = display_img.size
        text_width = img_width  # Same width as image
        
        # Prepare the text
        response_text = result.get("response", "No response")
        
        # Format the settings information
        settings_text = (
            f"Quality: {quality}%\n"
            f"Scale: {int(scale_factor*100)}% ({effective_max_dimension}px)\n"
            f"Temperature: {result['payload']['temperature']}\n"
            f"Time: {result['processing_time']:.2f}s"
        )
        
        # Calculate how much space we need for text
        text_height = int(len(response_text.split('\n')) * font_size * 1.5 + 200)
        text_height = max(text_height, img_height)
        
        # Create a new image with both parts
        combined_width = img_width + text_width
        combined_height = max(img_height, text_height)
        combined_img = Image.new('RGB', (combined_width, combined_height), (255, 255, 255))
        
        # Paste the display image on the left
        combined_img.paste(display_img, (0, 0))
        
        # Add text on the right
        draw = ImageDraw.Draw(combined_img)
        
        # Add settings at the top
        y_position = 10
        for line in settings_text.split('\n'):
            draw.text((img_width + 10, y_position), line, font=font, fill=(0, 0, 0))
            y_position += int(font_size * 1.5)
        
        # Add separator
        y_position += 10
        draw.line([(img_width + 10, y_position), (combined_width - 10, y_position)], fill=(0, 0, 0), width=1)
        y_position += 10
        
        # Add the response text
        line_height = int(font_size * 1.2)
        for line in response_text.split('\n'):
            # Wrap text if it's too long
            if int(len(line) * (font_size * 0.6)) > text_width - 20:
                words = line.split()
                current_line = ""
                for word in words:
                    test_line = current_line + " " + word if current_line else word
                    if int(len(test_line) * (font_size * 0.6)) < text_width - 20:
                        current_line = test_line
                    else:
                        draw.text((img_width + 10, y_position), current_line, font=font, fill=(0, 0, 0))
                        y_position += line_height
                        current_line = word
                if current_line:
                    draw.text((img_width + 10, y_position), current_line, font=font, fill=(0, 0, 0))
                    y_position += line_height
            else:
                draw.text((img_width + 10, y_position), line, font=font, fill=(0, 0, 0))
                y_position += line_height
        
        # Create appropriate filename based on scale and quality
        filename = os.path.basename(original_path)
        name, _ = os.path.splitext(filename)
        
        if scale_factor == 1.0 and quality == 100:
            output_filename = f"{name}_original_combined.jpg"
        elif scale_factor == 1.0:
            output_filename = f"{name}_q{quality}_combined.jpg"
        else:
            output_filename = f"{name}_s{int(scale_factor*100)}_q{quality}_combined.jpg"
            
        output_path = os.path.join(output_dir, output_filename)
        combined_img.save(output_path)
        
        return output_path
        
    except Exception as e:
        print(f"Error creating side-by-side image: {str(e)}")
        return None

def run_full_quality_cycle(file_path, api_url, api_password, output_dir, scale_factor):
    """Run a full quality reduction cycle for a specific scale factor"""
    processor = LLMProcessor(api_url, api_password)
    
    # Get scale string for display
    if scale_factor == 1.0:
        scale_str = "original (896px)"
    else:
        effective_dimension = int(896 * scale_factor)
        scale_str = f"{int(scale_factor*100)}% ({effective_dimension}px)"
    
    print(f"\n===== Processing scale: {scale_str} =====")
    
    # Process with all quality levels
    for quality in [100, 90, 70, 50, 30, 10]:
        print(f"  Processing quality: {quality}%")
        
        # Process the file
        result = processor.process_file(file_path, quality=quality, scale_factor=scale_factor)
        
        if result["success"]:
            # Create filename for JSON output
            filename = os.path.basename(file_path)
            name, _ = os.path.splitext(filename)
            
            if scale_factor == 1.0 and quality == 100:
                json_filename = f"{name}_original.json"
            elif scale_factor == 1.0:
                json_filename = f"{name}_q{quality}.json"
            else:
                json_filename = f"{name}_s{int(scale_factor*100)}_q{quality}.json"
            
            # Save JSON result
            json_path = os.path.join(output_dir, json_filename)
            
            # Remove any base64 data to keep JSON small
            result_for_json = {k: v for k, v in result.items() if k != 'image_base64'}
            
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result_for_json, f, indent=2)
            
            # Create side-by-side image
            side_by_side_path = create_side_by_side_image(file_path, result, output_dir)
            print(f"    Created: {os.path.basename(side_by_side_path) if side_by_side_path else 'Failed'}")
        else:
            print(f"    Failed: {result.get('error', 'Unknown error')}")

def main():
    parser = argparse.ArgumentParser(description="Process images with LLM API")
    parser.add_argument("--dir", required=True, help="Directory containing images to process")
    parser.add_argument("--api-url", default="http://localhost:5001", help="LLM API URL")
    parser.add_argument("--api-password", default="", help="LLM API password/token")
    parser.add_argument("--output-dir", help="Output directory (default: <input_dir>_results)")
    
    args = parser.parse_args()
    
    # Validate input directory
    if not os.path.isdir(args.dir):
        print(f"Error: {args.dir} is not a valid directory")
        return 1
    
    # Set default output directory if not specified
    if not args.output_dir:
        args.output_dir = f"{args.dir.rstrip('/')}_results"
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Get list of image files
    image_files = []
    for root, _, files in os.walk(args.dir):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                image_files.append(os.path.join(root, file))
    
    if not image_files:
        print(f"No image files found in {args.dir}")
        return 1
    
    print(f"Found {len(image_files)} image files to process")
    
    # Process each image
    for i, file_path in enumerate(image_files):
        print(f"[{i+1}/{len(image_files)}] Processing {file_path}")
        
        try:
            # For each image, process at 3 different scales
            scales = [1.0, 2/3, 1/3]  # Original, 67%, 33%
            
            for scale in scales:
                # For each scale, run full quality cycle
                run_full_quality_cycle(file_path, args.api_url, args.api_password, args.output_dir, scale)
                
        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")
    
    print(f"Processing complete. Results saved to {args.output_dir}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
