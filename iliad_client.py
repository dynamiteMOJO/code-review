import requests
from langchain_openai import AzureChatOpenAI
from langchain_anthropic import ChatAnthropic
from tenacity import retry, wait_exponential, stop_after_attempt
import os
from dotenv import load_dotenv

load_dotenv()

class IliadChatClient:
    def __init__(self, model_provider='anthropic', model_name='claude-sonnet-4-5-20250929'):
        """
        Initialize the Iliad AI client.

        Args:
            model_provider: Either 'openai' or 'anthropic'
            model_name: The specific model to use
        """
        # Load from env or use defaults
        self.client_id = os.getenv("ILIAD_CLIENT_ID", "YOUR_CLIENT_ID")
        self.client_secret = os.getenv("ILIAD_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
        self.token_url = os.getenv("ILIAD_TOKEN_URL", "https://iliad.example.com/oauth/token")
        self.endpoint = os.getenv("ILIAD_ENDPOINT", "https://iliad.example.com")

        # Get authentication token
        try:
             self.auth_token = self._get_auth_token()
        except Exception as e:
             # Fallback for local testing if auth fails/env not set
             print(f"Auth failed, using Mock Token: {e}")
             self.auth_token = "Bearer MOCK_TOKEN"

        # Initialize the appropriate model
        if model_provider == 'openai':
            # Note: Deployment name usually maps to model name in Azure
            deployment = os.getenv("AZURE_DEPLOYMENT_NAME", model_name)
            self.model = AzureChatOpenAI(
                azure_endpoint=self.endpoint,
                azure_deployment=deployment,
                api_key=self.auth_token.replace('Bearer ', ''),
                temperature=0.0,
                max_tokens=4096
            )
        elif model_provider == 'anthropic':
            self.model = ChatAnthropic(
                model=model_name,
                api_key=self.auth_token,
                base_url=f"{self.endpoint}/anthropic",
                temperature=0.0,
                max_tokens=4096,
                default_headers={"Authorization": self.auth_token}
            )
        else:
            raise ValueError(f"Unsupported provider: {model_provider}")

    def _get_auth_token(self):
        """Get OAuth2 bearer token from Iliad service."""
        # Check if dummy environment to avoid requests calls
        if "example.com" in self.token_url:
             return "Bearer MOCK_TOKEN"

        response = requests.post(
            url=self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        return f"Bearer {token}"

    @retry(wait=wait_exponential(multiplier=2, min=1, max=60), stop=stop_after_attempt(1))
    def generate(self, text_input):
        """
        Generate output from text input.

        Args:
            text_input: String or list of message dictionaries

        Returns:
            String response from the model
        """
        # Convert string input to message format if needed
        if isinstance(text_input, str):
            messages = [{"role": "user", "content": text_input}]
        else:
            messages = text_input

        # Call the model
        response = self.model.invoke(messages)
        return response.content
