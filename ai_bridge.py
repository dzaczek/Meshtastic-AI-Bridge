# ai_bridge.py
from openai import OpenAI
import google.generativeai as genai
import base64
import traceback

# Assuming web_utils.py is in the same directory and provides these functions:
# from web_utils import capture_screenshot_from_url_sync, extract_text_from_url
# For robustness, let's try to import and handle if it's missing, though it's a core part of URL analysis.
try:
    from web_utils import capture_screenshot_from_url_sync, extract_text_from_url
    WEB_UTILS_AVAILABLE = True
except ImportError:
    print("WARNING (ai_bridge.py): web_utils.py not found or 'capture_screenshot_from_url_sync' / 'extract_text_from_url' missing. URL analysis will be disabled.")
    WEB_UTILS_AVAILABLE = False
    # Define dummy functions if web_utils is not available to prevent NameError
    def capture_screenshot_from_url_sync(url, timeout_s=15): return None
    def extract_text_from_url(url, timeout_s=10): return None

# Import web spider for advanced data extraction
try:
    from web_spider import WebSpider, extract_weather_sync, search_duckduckgo_sync, extract_specific_data_sync
    WEB_SPIDER_AVAILABLE = True
except ImportError:
    print("WARNING (ai_bridge.py): web_spider.py not found. Advanced data extraction will be disabled.")
    WEB_SPIDER_AVAILABLE = False

# Import AI Web Agent for intelligent web scraping
try:
    from ai_web_agent import process_query_sync
    AI_WEB_AGENT_AVAILABLE = True
except ImportError:
    print("WARNING (ai_bridge.py): ai_web_agent.py not found. AI-powered web scraping will be disabled.")
    AI_WEB_AGENT_AVAILABLE = False


class AIBridge:
    def __init__(self, app_config):
        self.config = app_config
        self.current_ai_service = self.config.DEFAULT_AI_SERVICE
        self.current_persona = self.config.DEFAULT_PERSONA
        
        # Set web spider availability
        self.web_spider_available = WEB_SPIDER_AVAILABLE
        
        # Set AI Web Agent availability
        self.ai_web_agent_available = AI_WEB_AGENT_AVAILABLE
        
        # Main model names from config
        self.openai_model_name = getattr(self.config, 'OPENAI_MODEL_NAME', "gpt-3.5-turbo")
        self.openai_vision_model_name = getattr(self.config, 'OPENAI_VISION_MODEL_NAME', "gpt-4-vision-preview")
        self.gemini_text_model_name = getattr(self.config, 'GEMINI_TEXT_MODEL_NAME', "gemini-pro")
        self.gemini_vision_model_name = getattr(self.config, 'GEMINI_VISION_MODEL_NAME', "gemini-pro-vision")

        # AI Triage settings from config
        self.enable_ai_triage = getattr(self.config, 'ENABLE_AI_TRIAGE_ON_CHANNELS', False)
        self.triage_ai_service = getattr(self.config, 'TRIAGE_AI_SERVICE', 'openai')
        self.triage_ai_model_name = getattr(self.config, 'TRIAGE_AI_MODEL_NAME', 'gpt-3.5-turbo')
        self.triage_system_prompt_template = getattr(self.config, 'TRIAGE_SYSTEM_PROMPT', 
            ("You are a triage system for a main AI assistant. "
             "Decide if the main AI (persona: '{main_ai_persona}') should respond to NEWEST_MESSAGE "
             "based on it and RECENT_CHANNEL_HISTORY. "
             "Respond 'YES' if it's a question, engagement attempt, or relevant topic. "
             "Respond 'NO' for casual chatter not involving AI, simple acknowledgments, etc. "
             "Output ONLY 'YES' or 'NO'.")
        )
        self.triage_context_message_count = getattr(self.config, 'TRIAGE_CONTEXT_MESSAGE_COUNT', 3)


        self.openai_client = None
        if self.config.OPENAI_API_KEY and self.config.OPENAI_API_KEY not in ["sk-YOUR_OPENAI_API_KEY_HERE", ""]:
            try:
                self.openai_client = OpenAI(api_key=self.config.OPENAI_API_KEY)
                print("INFO (ai_bridge): OpenAI client initialized.")
            except Exception as e:
                print(f"WARNING (ai_bridge): Failed to initialize OpenAI client: {e}")
        else:
            print("WARNING (ai_bridge): OpenAI API key not configured. OpenAI functionality will be disabled.")

        self.gemini_text_model = None
        self.gemini_vision_model = None
        self.gemini_configured_successfully = False # General flag for Gemini
        if self.config.GEMINI_API_KEY and self.config.GEMINI_API_KEY not in ["YOUR_GEMINI_API_KEY_HERE", ""]:
            try:
                genai.configure(api_key=self.config.GEMINI_API_KEY)
                if hasattr(genai, 'GenerativeModel'):
                    # Initialize text model
                    try:
                        self.gemini_text_model = genai.GenerativeModel(self.gemini_text_model_name)
                        print(f"INFO (ai_bridge): Gemini text model ({self.gemini_text_model_name}) initialized.")
                        self.gemini_configured_successfully = True # At least text model is up
                    except Exception as text_model_e:
                        print(f"WARNING (ai_bridge): Could not initialize Gemini text model ({self.gemini_text_model_name}): {text_model_e}")

                    # Initialize vision model
                    try:
                        self.gemini_vision_model = genai.GenerativeModel(self.gemini_vision_model_name)
                        print(f"INFO (ai_bridge): Gemini vision model ({self.gemini_vision_model_name}) initialized.")
                    except Exception as vis_e:
                        print(f"WARNING (ai_bridge): Could not initialize Gemini Vision model ({self.gemini_vision_model_name}): {vis_e}.")
                        # self.gemini_vision_model remains None
                else:
                    print("WARNING (ai_bridge): genai.GenerativeModel not available. Gemini functionality limited.")
            except Exception as e:
                print(f"WARNING (ai_bridge): Failed to configure Gemini completely: {e}.")
        else:
            print("WARNING (ai_bridge): Gemini API key not configured. Gemini functionality will be disabled.")

    def set_ai_service(self, service_name):
        if service_name in ["openai", "gemini"]:
            self.current_ai_service = service_name
            print(f"INFO (ai_bridge): AI service switched to: {self.current_ai_service}")
        else:
            print(f"WARNING (ai_bridge): Unknown AI service: {service_name}. Keeping {self.current_ai_service}.")

    def set_persona(self, persona_text):
        self.current_persona = persona_text
        print(f"INFO (ai_bridge): AI Persona updated.")

    def _analyze_screenshot_with_openai(self, screenshot_bytes, url):
        if not self.openai_client:
            return "[OpenAI client not configured for vision.]"
        # print(f"DEBUG (ai_bridge): Sending screenshot of {url} to OpenAI Vision ({self.openai_vision_model_name})...")
        try:
            base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
            response = self.openai_client.chat.completions.create(
                model=self.openai_vision_model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"This is a screenshot of the webpage at {url}. Please provide a detailed analysis including: main headlines, key articles, navigation structure, and any notable content visible. Focus on information that would be useful for answering follow-up questions about the page content. Keep it under {getattr(self.config, 'MAX_WEB_SUMMARY_LENGTH', 800)} characters."},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                        ],
                    }
                ],
                max_tokens=500 
            )
            summary = response.choices[0].message.content.strip()
            return summary
        except Exception as e:
            print(f"ERROR (ai_bridge): OpenAI vision analysis for {url}: {e}")
            traceback.print_exc()
            return f"[Error analyzing screenshot with OpenAI Vision for {url}]"

    def _analyze_screenshot_with_gemini(self, screenshot_bytes, url):
        if not self.gemini_vision_model:
            return "[Gemini Vision model not configured or initialized.]"
        # print(f"DEBUG (ai_bridge): Sending screenshot of {url} to Gemini Vision ({self.gemini_vision_model_name})...")
        try:
            image_part = {"mime_type": "image/png", "data": screenshot_bytes}
            prompt_text = f"This is a screenshot of the webpage at {url}. Please provide a detailed analysis including: main headlines, key articles, navigation structure, and any notable content visible. Focus on information that would be useful for answering follow-up questions about the page content. Keep it under {getattr(self.config, 'MAX_WEB_SUMMARY_LENGTH', 800)} characters."
            
            response = self.gemini_vision_model.generate_content([prompt_text, image_part])
            summary = response.text.strip()
            return summary
        except Exception as e:
            print(f"ERROR (ai_bridge): Gemini vision analysis for {url}: {e}")
            traceback.print_exc()
            return f"[Error analyzing screenshot with Gemini Vision for {url}]"

    def analyze_url_content(self, url: str) -> str | None:
        if not WEB_UTILS_AVAILABLE:
            print("WARNING (ai_bridge): web_utils not available, cannot analyze URL content.")
            return f"[URL analysis not available - web_utils module missing]"
            
        print(f"INFO (ai_bridge): Starting analysis for URL: {url}")
        summary = None
        screenshot_bytes = capture_screenshot_from_url_sync(url, timeout_s=getattr(self.config, 'WEB_UTILS_TIMEOUT', 20))

        if screenshot_bytes:
            print(f"INFO (ai_bridge): Screenshot captured for {url}. Proceeding to AI vision analysis.")
            if self.current_ai_service == "openai":
                summary = self._analyze_screenshot_with_openai(screenshot_bytes, url)
            elif self.current_ai_service == "gemini":
                summary = self._analyze_screenshot_with_gemini(screenshot_bytes, url)
            else:
                summary = "[No AI service configured for vision analysis of screenshot.]"
        else:
            error_msg = f"Could not capture screenshot for {url}."
            print(f"WARNING (ai_bridge): {error_msg} Trying basic text extraction as fallback.")
            extracted_text = extract_text_from_url(url, timeout_s=getattr(self.config, 'WEB_UTILS_TIMEOUT', 20))
            if extracted_text:
                print(f"INFO (ai_bridge): Text extracted from {url}. Summarizing with text AI...")
                # Use the existing summarize_text method (which uses the current text AI)
                summary_of_extracted_text = self.summarize_text(
                    f"Content from webpage {url}: {extracted_text}", 
                    max_length=getattr(self.config, 'MAX_WEB_SUMMARY_LENGTH', 150)
                )
                if summary_of_extracted_text and not summary_of_extracted_text.lower().startswith("[summarization error"):
                    summary = f"Screenshot failed. Text summary for {url}: {summary_of_extracted_text}"
                else:
                    summary = f"{error_msg} Text extraction fallback also failed or yielded no summary. Extracted text (if any) was too long or unsummarizable."
            else:
                summary = f"{error_msg} Basic text extraction also failed for {url}."
        
        return summary if summary else f"[No analysis available for URL {url}]"

    def get_weather_data(self, city: str) -> str:
        """Get current weather data for a city using web spider"""
        if not self.web_spider_available:
            return f"[Weather data extraction not available - web_spider module missing]"
            
        print(f"INFO (ai_bridge): Getting weather data for {city}")
        try:
            weather_data = extract_weather_sync(city)
            if weather_data.get('temperature'):
                result = f"Weather in {city}: {weather_data['temperature']}°"
                if weather_data.get('condition'):
                    result += f", {weather_data['condition']}"
                if weather_data.get('source'):
                    result += f" (Source: {weather_data['source']})"
                return result
            else:
                return f"[Could not find weather data for {city}]"
        except Exception as e:
            print(f"ERROR (ai_bridge): Weather extraction failed: {e}")
            return f"[Error getting weather data for {city}]"

    def search_web(self, query: str, max_results: int = 3) -> str:
        """Search the web using DuckDuckGo and return results"""
        if not self.web_spider_available:
            return f"[Web search not available - web_spider module missing]"
            
        print(f"INFO (ai_bridge): Searching web for '{query}'")
        try:
            results = search_duckduckgo_sync(query, max_results)
            if results:
                result_text = f"Search results for '{query}':\n"
                for i, result in enumerate(results, 1):
                    result_text += f"{i}. {result['title']}"
                    if result.get('url'):
                        result_text += f" ({result['url']})"
                    result_text += "\n"
                return result_text
            else:
                return f"[No search results found for '{query}']"
        except Exception as e:
            print(f"ERROR (ai_bridge): Web search failed: {e}")
            return f"[Error searching for '{query}']"

    def extract_specific_info(self, url: str, info_type: str) -> str:
        """Extract specific information from a URL based on type"""
        if not self.web_spider_available:
            return f"[Specific data extraction not available - web_spider module missing]"
            
        print(f"INFO (ai_bridge): Extracting {info_type} from {url}")
        try:
            # Define selectors for different types of information
            selectors = {
                'temperature': ['.temp', '.temperature', '.weather-temp', '[data-temp]'],
                'price': ['.price', '.cost', '.amount', '[data-price]'],
                'title': ['h1', '.title', '.headline', '[data-title]'],
                'description': ['.description', '.summary', '.content', '.text'],
                'news': ['.news-item', '.article', '.story', '.post'],
                'weather': ['.weather', '.forecast', '.conditions']
            }
            
            if info_type not in selectors:
                return f"[Unknown info type: {info_type}. Available: {', '.join(selectors.keys())}]"
                
            # Try each selector for the given type
            for selector in selectors[info_type]:
                try:
                    data = extract_specific_data_sync(url, {info_type: selector})
                    if data.get(info_type):
                        return f"Found {info_type}: {data[info_type]}"
                except Exception as e:
                    continue
                    
            return f"[Could not extract {info_type} from {url}]"
            
        except Exception as e:
            print(f"ERROR (ai_bridge): Specific data extraction failed: {e}")
            return f"[Error extracting {info_type} from {url}]"

    def process_query_with_ai_agent(self, user_query: str) -> str:
        """Process a user query using AI Web Agent for intelligent web scraping"""
        if not self.ai_web_agent_available:
            return f"[AI Web Agent not available - ai_web_agent module missing]"
            
        if not self.openai_client:
            return f"[OpenAI client not available for AI Web Agent]"
            
        print(f"INFO (ai_bridge): Processing query with AI Web Agent: {user_query}")
        try:
            result = process_query_sync(user_query, self.openai_client)
            return result
        except Exception as e:
            print(f"ERROR (ai_bridge): AI Web Agent failed: {e}")
            return f"[Error processing query with AI Web Agent: {str(e)}]"

    def get_response_with_web_search(self, conversation_history, user_message_text, user_name="User", node_id="UnknownNode"):
        """Get AI response with automatic web search when needed"""
        if not self.openai_client:
            return "OpenAI client not available"
            
        # First, let AI analyze if web search is needed
        analysis_prompt = f"""
        Analyze this user message and decide if web search is needed to provide a good answer.
        
        User message: {user_message_text}
        
        Respond with JSON:
        {{
            "needs_web_search": true/false,
            "reason": "explanation why search is needed or not",
            "search_query": "optimized search query if needed"
        }}
        
        Examples:
        - "jaka jest pogoda" -> needs_web_search: true, search_query: "current weather"
        - "ile kosztuje frank" -> needs_web_search: true, search_query: "CHF exchange rate"
        - "jak się masz" -> needs_web_search: false
        - "opowiedz żart" -> needs_web_search: false
        """
        
        try:
            analysis_response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that analyzes if web search is needed."},
                    {"role": "user", "content": analysis_prompt}
                ],
                max_tokens=200
            )
            
            analysis_text = analysis_response.choices[0].message.content.strip()
            
            # Try to parse JSON
            try:
                import json
                analysis = json.loads(analysis_text)
                needs_search = analysis.get("needs_web_search", False)
                search_query = analysis.get("search_query", "")
                
                print(f"INFO (ai_bridge): Web search analysis: needs_search={needs_search}, query='{search_query}'")
                
                if needs_search and self.ai_web_agent_available:
                    print(f"INFO (ai_bridge): Using AI Web Agent for search")
                    web_result = self.process_query_with_ai_agent(search_query)
                    
                    # Add web search result to conversation context
                    enhanced_message = f"{user_message_text}\n\n[Web search result: {web_result}]"
                    
                    # Get AI response with web search context
                    return self.get_response(
                        conversation_history, 
                        enhanced_message, 
                        user_name, 
                        node_id,
                        web_analysis_summary=web_result
                    )
                else:
                    # Normal response without web search
                    return self.get_response(conversation_history, user_message_text, user_name, node_id)
                    
            except json.JSONDecodeError:
                print(f"WARNING (ai_bridge): Could not parse web search analysis: {analysis_text}")
                # Fallback to normal response
                return self.get_response(conversation_history, user_message_text, user_name, node_id)
                
        except Exception as e:
            print(f"ERROR (ai_bridge): Web search analysis failed: {e}")
            # Fallback to normal response
            return self.get_response(conversation_history, user_message_text, user_name, node_id)

    def get_response(self, conversation_history, user_message_text, user_name="User", node_id="UnknownNode", web_analysis_summary=None, skip_triage=False):
        if (self.current_ai_service == "openai" and not self.openai_client) or \
           (self.current_ai_service == "gemini" and not self.gemini_text_model): # Check primary text model
            print(f"ERROR (ai_bridge): {self.current_ai_service} text AI service not configured/available for get_response.")
            return None 

        user_attribution_for_ai = f"User (NodeID: {node_id})"
        if user_name and not user_name.startswith("Node-"):
            user_attribution_for_ai = f"User '{user_name}' (NodeID: {node_id})"
        
        messages_for_ai = [{"role": "system", "content": self.current_persona}]
        messages_for_ai.extend(conversation_history)

        current_turn_content_parts = []
        if web_analysis_summary:
            max_len_web_context = 1500 
            context_str = web_analysis_summary.strip()
            if len(context_str) > max_len_web_context:
                context_str = context_str[:max_len_web_context] + "..."
            current_turn_content_parts.append(f"[Context from analyzed URL: {context_str}]")
        
        current_turn_content_parts.append(f"{user_attribution_for_ai} says: {user_message_text}")
        final_user_content = "\n".join(current_turn_content_parts)
        messages_for_ai.append({"role": "user", "content": final_user_content})
        
        ai_reply_text = None
        try:
            if self.current_ai_service == "openai":
                # print(f"DEBUG (ai_bridge): Sending to OpenAI ({self.openai_model_name}): '{messages_for_ai[-1]['content'][:200]}...'")
                completion = self.openai_client.chat.completions.create(
                    model=self.openai_model_name,
                    messages=messages_for_ai
                )
                candidate_reply = completion.choices[0].message.content.strip()
                if candidate_reply: ai_reply_text = candidate_reply

            elif self.current_ai_service == "gemini":
                # print(f"DEBUG (ai_bridge): Sending to Gemini ({self.gemini_text_model_name}): '{messages_for_ai[-1]['content'][:200]}...'")
                gemini_chat_history_for_api = []
                system_instruction_for_gemini = None # Will be extracted if present

                for msg in messages_for_ai:
                    if msg['role'] == 'system':
                        system_instruction_for_gemini = msg['content'] # Capture system prompt
                        continue 
                    gemini_role = 'user' if msg['role'] == 'user' else 'model'
                    gemini_chat_history_for_api.append({'role': gemini_role, 'parts': [msg['content']]})
                
                if not gemini_chat_history_for_api or gemini_chat_history_for_api[-1]['role'] != 'user':
                    print("ERROR (ai_bridge): Gemini history malformed for API call: no user message at the end.")
                    return None
                
                current_user_prompt_parts = gemini_chat_history_for_api.pop()['parts']
                
                if not self.gemini_text_model:
                    print("ERROR (ai_bridge): Gemini text model not initialized.")
                    return None

                # Use a model instance possibly with system_instruction for this chat
                # If system_instruction_for_gemini was captured, use it.
                active_gemini_model = self.gemini_text_model # Default to pre-initialized one
                if system_instruction_for_gemini and system_instruction_for_gemini != self.current_persona:
                    # If a specific system message was in history beyond the default persona
                    active_gemini_model = genai.GenerativeModel(
                        model_name=self.gemini_text_model_name,
                        system_instruction=system_instruction_for_gemini
                    )
                elif system_instruction_for_gemini == self.current_persona: # Default persona as system instruction
                     active_gemini_model = genai.GenerativeModel(
                        model_name=self.gemini_text_model_name,
                        system_instruction=self.current_persona
                    )


                chat_session = active_gemini_model.start_chat(history=gemini_chat_history_for_api)
                response = chat_session.send_message(current_user_prompt_parts)
                candidate_reply = response.text.strip()
                if candidate_reply: ai_reply_text = candidate_reply

            if ai_reply_text: # Suppress non-answers
                suppress_phrases = ["i cannot fulfill", "i'm unable to", "i am unable", "as an ai", "i'm sorry, but i cannot", "...", "hmm"]
                ai_reply_lower = ai_reply_text.lower()
                
                # Adjust minimum length based on whether this is a DM (skip_triage=True) or channel message
                min_length = 3 if skip_triage else 5  # Allow shorter responses for DMs
                
                if not ai_reply_text.strip() or len(ai_reply_text.strip()) < min_length or \
                   any(phrase in ai_reply_lower for phrase in suppress_phrases):
                    print(f"INFO (ai_bridge): AI returned non-answer/refusal: '{ai_reply_text[:100]}...'. Suppressing.")
                    ai_reply_text = None
        except Exception as e:
            print(f"ERROR (ai_bridge): Exception during AI API call to {self.current_ai_service} for text response:")
            traceback.print_exc()
            ai_reply_text = None
        return ai_reply_text

    def summarize_text(self, text_to_summarize, max_length=100):
        if not text_to_summarize.strip(): return "[No text to summarize]"
        summary_persona = f"You are an expert at summarizing conversations or text very concisely into a single paragraph, under {max_length} characters, retaining key facts and context."
        summary_text = f"[Summarization by {self.current_ai_service} failed or not configured]"
        try:
            if self.current_ai_service == "openai" and self.openai_client:
                completion = self.openai_client.chat.completions.create(
                    model=self.openai_model_name,
                    messages=[{"role": "system", "content": summary_persona},
                              {"role": "user", "content": text_to_summarize}]
                )
                summary_text = completion.choices[0].message.content.strip()
            elif self.current_ai_service == "gemini" and self.gemini_text_model:
                 model_for_summary = genai.GenerativeModel(
                    model_name=self.gemini_text_model_name,
                    system_instruction=summary_persona
                )
                 response = model_for_summary.generate_content(text_to_summarize) # Let persona guide summary length
                 summary_text = response.text.strip()
            
            if len(summary_text) > max_length + 30: # Allow more leeway for summary models
                summary_text = summary_text[:max_length] + "..." 
            return summary_text
        except Exception as e:
            print(f"ERROR (ai_bridge): Error summarizing text with {self.current_ai_service}:")
            traceback.print_exc()
            return f"[Summarization error by {self.current_ai_service}]"

    def should_main_ai_respond(self, recent_channel_history: list[str], newest_message_text: str, newest_message_sender: str) -> bool:
        """
        Uses a simpler AI call to decide if the main AI should process and respond to a channel message.
        """
        if not self.enable_ai_triage: # Use the flag from __init__
            return True # Triage disabled, so assume AI should consider responding based on other rules

        # Select triage service and model
        triage_service_to_use = self.triage_ai_service
        triage_model_to_use = self.triage_ai_model_name
        
        # Check if the selected triage service is available
        if triage_service_to_use == "openai" and not self.openai_client:
            print(f"WARNING (ai_bridge Triage): OpenAI client not available for triage. Defaulting to YES.")
            return True
        if triage_service_to_use == "gemini" and not self.gemini_text_model: # Use text model for triage
            print(f"WARNING (ai_bridge Triage): Gemini text model not available for triage. Defaulting to YES.")
            return True

        main_persona_summary = self.current_persona
        if len(main_persona_summary) > 250: 
            main_persona_summary = self.current_persona[:247] + "..."
            
        triage_system_prompt_filled = self.triage_system_prompt_template.format(main_ai_persona=main_persona_summary)
        
        history_str = "\n".join(recent_channel_history[-self.triage_context_message_count:])
        
        full_triage_query = (
            f"RECENT_CHANNEL_HISTORY:\n{history_str}\n\n"
            f"NEWEST_MESSAGE from '{newest_message_sender}':\n{newest_message_text}\n\n"
            f"Considering the main AI's persona and the instructions, should the main AI generate a response to the NEWEST_MESSAGE? (Answer ONLY 'YES' or 'NO')"
        )

        # print(f"DEBUG (ai_bridge Triage): Sending to {triage_service_to_use} ({triage_model_to_use}) for triage.")
        # print(f"DEBUG (ai_bridge Triage): System Prompt: {triage_system_prompt_filled}")
        # print(f"DEBUG (ai_bridge Triage): Query: {full_triage_query}")

        try:
            if triage_service_to_use == "openai":
                completion = self.openai_client.chat.completions.create(
                    model=triage_model_to_use,
                    messages=[
                        {"role": "system", "content": triage_system_prompt_filled},
                        {"role": "user", "content": full_triage_query}
                    ],
                    max_tokens=5, temperature=0.0
                )
                decision = completion.choices[0].message.content.strip().upper()
                print(f"INFO (ai_bridge Triage): OpenAI Triage decision: '{decision}' for message from {newest_message_sender}")
                return decision == "YES"

            elif triage_service_to_use == "gemini":
                # Use a model instance with the triage system instruction
                triage_gemini_instance = genai.GenerativeModel(
                    model_name=triage_model_to_use,
                    system_instruction=triage_system_prompt_filled
                )
                response = triage_gemini_instance.generate_content(full_triage_query)
                decision = response.text.strip().upper()
                print(f"INFO (ai_bridge Triage): Gemini Triage decision: '{decision}' for message from {newest_message_sender}")
                return decision == "YES"
            else:
                print(f"WARNING (ai_bridge Triage): Triage AI service '{triage_service_to_use}' not supported. Defaulting to YES.")
                return True

        except Exception as e:
            print(f"ERROR (ai_bridge Triage): Exception during AI Triage call to {triage_service_to_use}: {e}")
            traceback.print_exc()
            return True # Fallback on error to allow main AI to respond (safer than silencing on triage error)


