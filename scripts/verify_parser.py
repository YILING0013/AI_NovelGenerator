
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from novel_generator.architecture_parser import load_architecture

def verify():
    # Detect dynamically as per new logic, but for test we know it's wxhyj
    novel_dir = os.path.join(os.getcwd(), 'wxhyj') 
    
    print(f"Loading architecture from: {novel_dir}")
    data = load_architecture(novel_dir)
    
    print("-" * 30)
    print(f"Title: {data.title}")
    print(f"Chapters: {data.total_chapters}")
    print(f"Target Words: {data.target_words}")
    print("-" * 30)
    print("Plot Arcs:")
    for arc in data.plot_arcs:
        print(f"  Vol {arc.volume}: {arc.name} ({arc.start_chapter}-{arc.end_chapter})")
        print(f"    Events found: {len(arc.key_events)}")
        if arc.key_events:
            print(f"    Sample: {arc.key_events[0]}")
    print("-" * 30)
    
    if data.title and len(data.plot_arcs) >= 5:
        print("✅ VERIFICATION PASSED")
    else:
        print("❌ VERIFICATION FAILED")

if __name__ == "__main__":
    verify()
