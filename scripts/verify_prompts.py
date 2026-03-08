
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import prompt_definitions
except ImportError:
    print("Error: Could not import prompt_definitions.py")
    sys.exit(1)

def verify_no_hardcoding():
    banned_words = ["张昊", "林小雨", "苏清雪", "赵四", "青冥", "玄冰子", "云渺渺", "魔心莲"]
    
    # Get all attributes
    attributes = [a for a in dir(prompt_definitions) if not a.startswith('__')]
    
    found_issues = []
    
    print(f"Loading prompt_definitions from: {prompt_definitions.__file__}")
    
    for attr_name in attributes:
        attr_value = getattr(prompt_definitions, attr_name)
        if isinstance(attr_value, str):
            for word in banned_words:
                if word in attr_value:
                    index = attr_value.find(word)
                    context = attr_value[max(0, index-20):min(len(attr_value), index+20)]
                    found_issues.append(f"Attribute '{attr_name}' contains hardcoded word: '{word}'. Context: ...{context.replace(chr(10), ' ')}...")
                    # Break to avoid printing multiple times for same attribute
                    break 
        elif isinstance(attr_value, list):
             for i, item in enumerate(attr_value):
                 if isinstance(item, str):
                     for word in banned_words:
                         if word in item:
                             found_issues.append(f"Attribute '{attr_name}' (list item {i}) contains hardcoded word: '{word}'")
                             break
        elif isinstance(attr_value, dict):
             # Simple shallow check for dict values
             for k, v in attr_value.items():
                 if isinstance(v, str):
                     for word in banned_words:
                         if word in v:
                             found_issues.append(f"Attribute '{attr_name}' (key {k}) contains hardcoded word: '{word}'")
                             break
    
    if found_issues:
        print(f"❌ Found {len(found_issues)} hardcoded artifacts:")
        for issue in found_issues:
            print(f"  - {issue}")
        print("\nVerification FAILED.")
        sys.exit(1)
    else:
        print("✅ No hardcoded artifacts found in prompt_definitions.py!")
        sys.exit(0)

if __name__ == "__main__":
    verify_no_hardcoding()
