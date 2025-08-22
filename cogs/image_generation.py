import os
import io
import base64
from google.cloud import aiplatform
import PIL.Image

# --- IMPORTANT: CONFIGURATION ---
# You must set these environment variables or fill them in below.
# PROJECT_ID is your Google Cloud project ID.
# LOCATION is the region where you want to run the model (e.g., "us-central1").
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "your-project-id")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

# The model name for image generation.
MODEL_NAME = "imagen-3.0"

# --- Main Function for Image Generation ---
async def generate_image_from_prompt(prompt: str) -> bytes | None:
    """
    Generates an image from a text prompt using the Google Cloud Vertex AI API (Imagen).
    Returns the bytes of the generated image, or None on failure.

    Args:
        prompt: The text description of the image to generate.

    Returns:
        The bytes of the generated image, or None on failure.
    """
    try:
        # Initialize the Vertex AI client
        aiplatform.init(project=PROJECT_ID, location=LOCATION)
        
        # Load the Imagen model
        model = aiplatform.ImageGenerationModel.from_pretrained(MODEL_NAME)
        
        # Use a high-quality prompt for the best results
        image_generation_prompt = f"Generate a highly detailed, professional-quality image of the following scene: {prompt}"

        # Generate the image. The model returns a response with a base64-encoded image.
        response = model.generate_images(
            prompt=image_generation_prompt,
            number_of_images=1
        )
        
        if response.images:
            # The API returns a PIL.Image object.
            image_object = response.images[0]._image
            
            # Convert the PIL.Image object to bytes for Discord.
            with io.BytesIO() as image_bytes:
                image_object.save(image_bytes, format="PNG")
                return image_bytes.getvalue()
        
        print("ERROR: Vertex AI image generation returned no images.")
        return None

    except Exception as e:
        print(f"ERROR: Image generation with Vertex AI failed: {e}")
        return None
