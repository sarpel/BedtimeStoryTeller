import argparse

def main():
    parser = argparse.ArgumentParser(description="Bedtime Storyteller Gadget")
    parser.add_argument("prompt", type=str, help="The topic of the story (e.g., 'a curious little fox').")
    parser.add_argument("--provider", type=str, default="openai", choices=["openai", "ollama"], help="The AI provider to use for story generation.")
    parser.add_argument("--voice", type=str, default="alloy", help="The voice to use for narration.")
    
    args = parser.parse_args()
    
    print(f"Generating a story about: '{args.prompt}' using {args.provider} with '{args.voice}' voice.")
    # Burada agent çağrılır ve hikaye süreci başlatılır.
    # from agent.agent import StorytellingAgent
    # agent = StorytellingAgent(provider_name=args.provider)
    # agent.tell_story(args.prompt, voice=args.voice)

if __name__ == "__main__":
    main()