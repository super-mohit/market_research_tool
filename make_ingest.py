# make_ingest.py

import sys
import subprocess

def generate_digest_cli(source, output_file="digest.txt", exclude_exts=None):
    cmd = ["gitingest", source, "-o", output_file]
    
    # Always exclude reports directory
    exclusions = ["reports", "reports/*", "extractions", "extractions/*", "logs.txt", "__pycache__"]
    
    if exclude_exts:
        # Format extensions as "*.ext" and add to exclusions
        exclusions.extend(f"*{ext}" for ext in exclude_exts)

    if exclusions:
        patterns = ",".join(exclusions)
        cmd += ["-e", patterns]

    print("Running:", " ".join(cmd))

    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Digest written to {output_file}")
    except subprocess.CalledProcessError as e:
        print("❌ Error during gitingest execution:", e)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python make_ingest.py <path_or_url> [output_file] [excluded_exts...]")
        sys.exit(1)

    source = sys.argv[1]
    
    # Determine if second argument is an output file or an extension
    output_file = "digest.txt"
    exclude_exts = []

    if len(sys.argv) >= 3 and sys.argv[2].startswith(".") is False:
        output_file = sys.argv[2]
        exclude_exts = sys.argv[3:]
    else:
        exclude_exts = sys.argv[2:]

    generate_digest_cli(source, output_file, exclude_exts)
