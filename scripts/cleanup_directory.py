
import os

file_path = r'c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj\Novel_directory.txt'

# 1-based ranges to delete (inclusive)
ranges_to_delete = [
    (84, 146),   # Ch 2 Format A
    (199, 235),  # Ch 3 Format A
    (306, 344),  # Ch 4 Format A
    (407, 479),  # Ch 5 Format A
    (631, 677),  # Ch 7 Format A
    (742, 791),  # Ch 8 Format A
    (856, 895),  # Ch 9 Format A
    (961, 1015)  # Ch 10 Format A
]

def clean_file():
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print(f"Original line count: {len(lines)}")

    # Create a set of indices to delete (0-based)
    indices_to_delete = set()
    for start, end in ranges_to_delete:
        # Convert 1-based [start, end] to 0-based [start-1, end-1]
        for i in range(start - 1, end):
            indices_to_delete.add(i)

    new_lines = []
    for i, line in enumerate(lines):
        if i not in indices_to_delete:
            new_lines.append(line)

    print(f"New line count: {len(new_lines)}")

    # Backup original
    backup_path = file_path + ".bak"
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"Backup saved to {backup_path}")

    # Write cleaned content
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print(f"Successfully wrote cleaned content to {file_path}")

if __name__ == "__main__":
    clean_file()
