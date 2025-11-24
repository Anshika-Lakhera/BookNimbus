import os

# Path to your project folder
project_path = r"C:\Users\test\Documents\BookNimbus\app"

# Output file
output_file = "all_files_combined.txt"

with open(output_file, "w", encoding="utf-8") as out_f:
    for root, dirs, files in os.walk(project_path):
        for file in files:
            file_path = os.path.join(root, file)
            # Get relative path from the project root
            relative_path = os.path.relpath(file_path, project_path)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # Write relative path and content
                out_f.write(f"{relative_path}\n")
                out_f.write(content + "\n\n")
            except Exception as e:
                print(f"Skipping {file_path}: {e}")

print(f"All files have been combined into {output_file}")
