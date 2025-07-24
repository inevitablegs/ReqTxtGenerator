#!/usr/bin/env python3
import os
import sys
import importlib.metadata
import google.generativeai as genai

# ===================================================================================
# --- SCRIPT CONFIGURATION ---
# ===================================================================================

# This map helps correct Gemini's output if it provides an import name
# instead of the actual PyPI package name. It acts as a helpful fallback.
IMPORT_TO_PYPI_MAP = {
    'bs4': 'beautifulsoup4',
    'cv2': 'opencv-python',
    'dateutil': 'python-dateutil',
    'dotenv': 'python-dotenv',
    'PIL': 'Pillow',
    'sklearn': 'scikit-learn',
    'yaml': 'PyYAML',
    'rest_framework': 'djangorestframework',
    'corsheaders': 'django-cors-headers',
    'jose': 'python-jose',
    'jwt': 'PyJWT',
    'youtube_search': 'youtube-search',
}

# The model to use. 'gemini-1.5-flash' is fast and cost-effective for this task.
GEMINI_MODEL_NAME = 'gemini-1.5-flash'


# ===================================================================================
# --- CORE LOGIC ---
# ===================================================================================

class GeminiRequirementsGenerator:
    """
    Generates requirements.txt by analyzing the entire project's codebase with Gemini.
    """
    def __init__(self, root_dir, api_key):
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set.")
        self.root_dir = os.path.abspath(root_dir)
        self.api_key = api_key
        self.project_code = ""
        self.final_requirements = {}

    def _ingest_project_code(self):
        """
        Acts like 'gitingest' to scrape all relevant source code into a single string.
        """
        print("Step 1: Ingesting project source code...")
        code_files = []
        exclude_dirs = {'.venv', 'venv', 'env', 'build', 'dist', '.git', '__pycache__', 'node_modules'}
        exclude_files = {'gemini_reqs.py', 'requirements.txt'} # Don't include this script itself

        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
            for filename in filenames:
                if filename.endswith('.py') and filename not in exclude_files:
                    file_path = os.path.join(dirpath, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            relative_path = os.path.relpath(file_path, self.root_dir)
                            # Add a header to give the LLM context for each file
                            code_files.append(f"--- FILE: {relative_path} ---\n\n{f.read()}")
                    except Exception as e:
                        print(f"   - Warning: Could not read {file_path}: {e}")
        
        if not code_files:
            raise RuntimeError("No Python source files found to analyze.")

        self.project_code = "\n\n".join(code_files)
        print(f"   ...ingested {len(code_files)} Python files.")

    def _get_packages_from_gemini(self):
        """
        Sends the ingested code to the Gemini API and asks it to identify dependencies.
        """
        print("\nStep 2: Asking Gemini to analyze the code... (this may take a moment)")
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)

        prompt = f"""
You are an expert Python dependency analysis tool. Your task is to analyze the following Python code, which has been concatenated from multiple files in a project.

Your goal is to identify all third-party, pip-installable libraries that are being used.

Follow these rules STRICTLY:
1.  **ONLY list third-party packages.**
2.  **DO NOT include Python's standard library modules.** Examples to exclude: os, sys, json, datetime, re, logging, pathlib, ast, subprocess, math, collections, itertools.
3.  **DO NOT include local modules** that are part of the project itself. The file paths are provided for context.
4.  **Provide the canonical PyPI package name where possible** (e.g., 'djangorestframework' instead of 'rest_framework', 'beautifulsoup4' instead of 'bs4').
5.  **Format your output as a single, clean, comma-separated list.** Do not add any other text, explanation, or formatting.

Example of a perfect response:
django,djangorestframework,requests,beautifulsoup4,google-generativeai,python-dotenv,gunicorn

--- PROJECT CODE ---

{self.project_code}
"""
        try:
            response = model.generate_content(prompt)
            print("   ...Gemini analysis complete.")
            return response.text
        except Exception as e:
            print(f"   - Error: An error occurred with the Gemini API: {e}")
            sys.exit(1)

    def _parse_and_resolve_versions(self, gemini_output):
        """
        Parses Gemini's comma-separated list and resolves the version for each package.
        """
        print("\nStep 3: Resolving package versions from your environment...")
        if not gemini_output:
            print("   - Warning: Gemini returned an empty response. No packages found.")
            return

        potential_packages = [pkg.strip() for pkg in gemini_output.strip().split(',') if pkg.strip()]

        for pkg_name in sorted(potential_packages):
            # Use the map as a first-pass correction
            corrected_name = IMPORT_TO_PYPI_MAP.get(pkg_name, pkg_name)
            
            try:
                # importlib.metadata is the source of truth for installed packages
                dist = importlib.metadata.distribution(corrected_name)
                pypi_name = dist.metadata['Name']
                version = dist.version
                if pypi_name not in self.final_requirements:
                    print(f"  [+] Found: {pypi_name}=={version}")
                    self.final_requirements[pypi_name] = version
            except importlib.metadata.PackageNotFoundError:
                print(f"  [-] Warning: Gemini suggested '{pkg_name}', but it's not installed or could not be found.")

    def write_file(self, output_file='requirements.txt'):
        """Writes the final list of packages to the requirements file."""
        print("-" * 60)
        print(f"Writing {len(self.final_requirements)} packages to '{output_file}'...")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# Generated by Gemini AI. Review for accuracy.\n")
            f.write("# This file lists the direct dependencies identified from the source code.\n\n")

            for package, version in sorted(self.final_requirements.items(), key=lambda item: item[0].lower()):
                f.write(f"{package}=={version}\n")
        
        print(f"✅ Successfully generated '{output_file}'.")

    def run(self):
        """Executes the full generation process."""
        self._ingest_project_code()
        gemini_response = self._get_packages_from_gemini()
        self._parse_and_resolve_versions(gemini_response)
        self.write_file()


def main():
    """Main execution function."""
    print("=" * 60)
    print("🤖 Gemini AI Requirements Generator")
    print("=" * 60)

    # Ensure you are in a virtual environment
    if not (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)):
         print("🚨 WARNING: You do not appear to be in a Python virtual environment.")
         print("   This script relies on your active environment to find package versions.")
         print("-" * 60)

    try:
        api_key = os.getenv('GOOGLE_API_KEY')
        generator = GeminiRequirementsGenerator(root_dir='.', api_key=api_key)
        generator.run()
    except ValueError as e:
        print(f"Error: {e}")
        print("\nPlease set your GOOGLE_API_KEY as an environment variable.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()