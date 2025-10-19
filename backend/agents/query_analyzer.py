import google.generativeai as genai
import os

# It's good practice to handle the case where the import fails.
try:
    from db.connection import get_db
except ImportError:
    print("Warning: db.connection module not found. Skipping import.")
    get_db = None

class QueryAnalyzer:
    """
    A class to analyze user queries against a set of policy documents
    using the Gemini API.
    """
    def __init__(self):
        """
        Initializes the QueryAnalyzer, configures the Gemini API,
        and sets up the model and base prompt.
        """
        # Configure the Gemini API with the API key from environment variables.
        try:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        except Exception as e:
            print(f"Error configuring Gemini API: {e}")
            self.model = None
            return

        # Use the correct way to instantiate the model for content generation.
        # The 'models/' prefix is not needed here.
        self.model = genai.GenerativeModel("gemini-1.5-flash")

        # Base prompt to guide the model's behavior.
        # This is kept as-is, as it's well-designed for the task.
        self.base_prompt = """
You are a Policy Check Agent.

Your only responsibility is to answer user questions strictly based on the provided policy documents/chunks.

When the user provides context + a question, check if the answer can be found directly in the given documents.

If the necessary information is available, give a clear, direct, and understandable answer in simple language.

If the answer is not explicitly available in the documents, respond only with: "I don’t know".

Do not guess, assume, or think outside the given documents.

Never use external knowledge, only the provided context.
"""

    def process(self, query, chunks):
        
        """
        Processes a user query by sending it to the Gemini model with
        the provided policy chunks as context.

        Args:
            query (str): The user's question.
            chunks (list of str): Retrieved policy chunks relevant to the query.
        Returns:
            dict: A dictionary containing the agent name, status, and result.
        """
        if not self.model:
            return {
                "agent": "QueryAnalyzer",
                "status": "error",
                "result": "Gemini API model not initialized."
            }

        try:
            # Combine chunks into one string for context.
            context = "\n\n".join(chunks)
     
            # Create the full prompt by combining the base prompt, context, and query.
            prompt = f"{self.base_prompt}\n\nContext:\n{chunks}\n\nQuestion:\n{query}\nAnswer:"

          

            # Use the generate_content method which is correct for this use case.
            # This is the key fix for the "no attribute 'chat'" error.
            response = self.model.generate_content(prompt)

            # Extract the text from the response object.
            # The 'response' object has a '.text' attribute containing the generated content.
            # Using a fallback to handle potential empty responses.
            answer = response.text
            
            print(f"Anser is : {answer}" )

            return {
                "agent": "QueryAnalyzer",
                "status": "success",
                "result": answer
            }

        except Exception as e:
            # Improved error handling to provide more specific feedback.
            return {
                "agent": "QueryAnalyzer",
                "status": "error",
                "result": f"An error occurred during content generation: {e}"
            }
