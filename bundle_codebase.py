import os
from pathlib import Path
from datetime import datetime

def bundle_codebase(root_path: Path, output_filename: str):
    """
    Traverses the project directory and bundles all source code into a single text file.
    Designed for uploading full context to AI systems.
    """
    # Define file types to include
    include_extensions = {'.py', '.md', '.json', '.yaml', '.yml', '.html', '.css', '.js'}
    
    # Define directories to skip to keep the file size manageable and relevant
    exclude_dirs = {'.git', '__pycache__', 'venv', '.venv', 'data', 'logs', 'reports', 'dist', 'build', 'node_modules'}

    with open(output_filename, 'w', encoding='utf-8') as outfile:
        outfile.write(f"FILEFLOW FULL SYSTEM DUMP\n")
        outfile.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        outfile.write("="*80 + "\n\n")

        for root, dirs, files in os.walk(root_path):
            # Modifying dirs in-place allows os.walk to skip them
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                file_path = Path(root) / file
                
                if file_path.suffix.lower() in include_extensions:
                    # Skip the output file itself if it's already in the directory
                    if file == output_filename:
                        continue
                        
                    relative_path = file_path.relative_to(root_path)
                    
                    outfile.write(f"\n{'#'*100}\n")
                    outfile.write(f"### PATH: {relative_path}\n")
                    outfile.write(f"{'#'*100}\n\n")
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='replace') as infile:
                            outfile.write(infile.read())
                    except Exception as e:
                        outfile.write(f"// Error reading file {relative_path}: {e}\n")
                    
                    outfile.write("\n\n")

if __name__ == "__main__":
    # Set root to the directory where this script is located
    project_root = Path(__file__).parent.absolute()
    output_file = "fileflow_full_system.txt"
    
    print(f"Bundling FileFlow codebase from {project_root}...")
    bundle_codebase(project_root, output_file)
    print(f"Success! Full system dump created: {output_file}")