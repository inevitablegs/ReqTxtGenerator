import os
import sys
import ast
import importlib.metadata

# ===================================================================================
# --- SCRIPT CONFIGURATION ---
# This is the main section you might need to edit.
# ===================================================================================

# The key to accuracy. Maps non-obvious `import` names to their PyPI package names.
# This list is comprehensive but you can add your project's specific packages.
IMPORT_TO_PYPI_MAP = {
    # Common Django Packages
    'corsheaders': 'django-cors-headers',
    'rest_framework': 'djangorestframework',
    'rest_framework_simplejwt': 'djangorestframework-simplejwt',
    'django_filters': 'django-filter',
    'crispy_forms': 'django-crispy-forms',
    'cloudinary_storage': 'django-cloudinary-storage',

    # Common Web & API Packages
    'bs4': 'beautifulsoup4',
    'dateutil': 'python-dateutil',
    'dotenv': 'python-dotenv',
    'jose': 'python-jose',
    'jwt': 'PyJWT',
    'PIL': 'Pillow',
    'werkzeug': 'Werkzeug',      # Part of Flask
    'jinja2': 'Jinja2',         # Part of Flask

    # Data Science & AI
    'cv2': 'opencv-python',
    'faiss': 'faiss-cpu',        # Or 'faiss-gpu'
    'sklearn': 'scikit-learn',
    'tavily': 'tavily-python',
    'yaml': 'PyYAML',

    # Database & Drivers
    'psycopg2': 'psycopg2-binary',
    'MySQLdb': 'mysqlclient',

    # Utilities & Others
    'Crypto': 'pycryptodome',
    'pkg_resources': 'setuptools',
    'youtube_search': 'youtube-search',
}

# Packages often used from the command line or via config strings, which may not be
# found by scanning `import` statements. The script checks if these are installed.
KNOWN_CLI_AND_CONFIG_TOOLS = {
    'gunicorn',
    'uvicorn',
    'daphne',
    'whitenoise',
    'black',
    'isort',
    'flake8',
    'mypy',
    'pytest',
    'pip-tools',
}

# ===================================================================================
# --- CORE LOGIC ---
# You should not need to edit below this line.
# ===================================================================================

class RequirementsGenerator:
    """
    Scans a Python project to generate a requirements.txt file based on actual usage.
    """
    def __init__(self, root_dir):
        self.root_dir = os.path.abspath(root_dir)
        self.std_lib = self._get_std_lib_modules()
        self.local_modules = self._find_local_modules()
        self.final_requirements = {}
        self.unresolved_imports = set()

    def _get_std_lib_modules(self):
        if sys.version_info >= (3, 10):
            return sys.stdlib_module_names
        # Fallback for older Python versions
        print("Warning: Using a limited standard library list for Python < 3.10.")
        return {'os', 'sys', 'math', 'datetime', 'json', 're', 'logging', 'collections',
                'itertools', 'functools', 'pathlib', 'subprocess', 'ast', 'importlib'}

    def _find_local_modules(self):
        """Finds directories that are Python packages to identify local modules."""
        local_modules = set()
        for dirpath, _, filenames in os.walk(self.root_dir):
            if '__init__.py' in filenames:
                package_name = os.path.basename(dirpath)
                local_modules.add(package_name)
        local_modules.add(os.path.basename(self.root_dir))
        return local_modules

    def _get_package_info(self, name):
        """Gets (version, pypi_name) for a given potential package name."""
        try:
            dist = importlib.metadata.distribution(name)
            return dist.version, dist.metadata['Name']
        except importlib.metadata.PackageNotFoundError:
            return None, None

    def _scan_python_files(self):
        """Scans all .py files for top-level import statements."""
        imports = set()
        exclude_dirs = {'.venv', 'venv', 'env', 'build', 'dist', '.git', '__pycache__', 'node_modules'}
        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
            for filename in filenames:
                if not filename.endswith('.py'): continue
                file_path = os.path.join(dirpath, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as file:
                        tree = ast.parse(file.read(), filename=file_path)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    imports.add(alias.name.split('.')[0])
                            elif isinstance(node, ast.ImportFrom):
                                if node.level > 0: continue
                                if node.module:
                                    imports.add(node.module.split('.')[0])
                except Exception:
                    pass
        return imports

    def _scan_django_settings(self):
        """Parses Django settings.py for INSTALLED_APPS and MIDDLEWARE."""
        found_modules = set()
        for dirpath, _, filenames in os.walk(self.root_dir):
            if 'settings.py' in filenames and 'manage.py' in os.listdir(os.path.dirname(dirpath)):
                settings_file = os.path.join(dirpath, 'settings.py')
                try:
                    with open(settings_file, 'r', encoding='utf-8') as f:
                        tree = ast.parse(f.read(), filename=settings_file)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Assign):
                                for target in node.targets:
                                    if isinstance(target, ast.Name) and target.id in ('INSTALLED_APPS', 'MIDDLEWARE'):
                                        if isinstance(node.value, (ast.List, ast.Tuple)):
                                            for element in node.value.elts:
                                                if isinstance(element, ast.Constant):
                                                    found_modules.add(element.value.split('.')[0])
                                                elif isinstance(element, ast.Str):
                                                    found_modules.add(element.s.split('.')[0])
                except Exception as e:
                    print(f"Warning: Could not parse Django settings file at {settings_file}: {e}")
                return found_modules # Assume one settings file is enough
        return found_modules

    def run(self):
        """Executes the full scan and resolution process."""
        print("--- Step 1: Scanning project for imports ---")
        discovered_imports = self._scan_python_files()
        django_imports = self._scan_django_settings()
        discovered_imports.update(django_imports)
        print(f"Found {len(discovered_imports)} unique potential module names.")

        print("\n--- Step 2: Filtering out standard library and local modules ---")
        external_imports = {
            imp for imp in discovered_imports
            if imp and imp not in self.std_lib and imp not in self.local_modules
        }
        print(f"Filtered down to {len(external_imports)} potential external packages.")

        print("\n--- Step 3: Resolving package names and versions ---")
        for imp in sorted(list(external_imports)):
            pypi_name_to_check = IMPORT_TO_PYPI_MAP.get(imp, imp)
            version, pypi_name = self._get_package_info(pypi_name_to_check)
            if pypi_name:
                if pypi_name not in self.final_requirements:
                    print(f"  [+] Found: {pypi_name}=={version} (from import '{imp}')")
                    self.final_requirements[pypi_name] = version
            else:
                self.unresolved_imports.add(imp)

        print("\n--- Step 4: Checking for known command-line tools ---")
        for tool in KNOWN_CLI_AND_CONFIG_TOOLS:
            if tool in self.final_requirements: continue
            version, pypi_name = self._get_package_info(tool)
            if pypi_name:
                print(f"  [+] Found: {pypi_name}=={version} (as a known tool)")
                self.final_requirements[pypi_name] = version

    def write_file(self, output_file='requirements.txt'):
        """Writes the resolved dependencies to the output file."""
        print("-" * 60)
        print(f"Writing {len(self.final_requirements)} packages to '{output_file}'...")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# Generated by project scanner. Review for accuracy.\n")
            f.write("# This file lists direct dependencies. Sub-dependencies are handled by pip.\n\n")

            for package, version in sorted(self.final_requirements.items(), key=lambda item: item[0].lower()):
                line = f"{package}=={version}\n" if version else f"{package}\n"
                f.write(line)

        print("✅ Generation complete.")
        
        if self.unresolved_imports:
            print("\n⚠️  The following imports could not be resolved to an installed package:")
            print("   " + ", ".join(sorted(list(self.unresolved_imports))))
            print("   - Ensure the package is installed in your virtual environment (`pip install ...`).")
            print("   - If the import name differs from the PyPI name, add it to `IMPORT_TO_PYPI_MAP`.")


def main():
    """Main execution function."""
    project_directory = '.'
    print(f"Starting requirements generation for directory: '{os.path.abspath(project_directory)}'")
    print("-" * 60)
    
    if not sys.prefix.startswith(os.getcwd()):
         print("🚨 WARNING: You may not be in an active virtual environment for this project.")
         print(f"   Sys prefix: {sys.prefix}")
         print(f"   Project dir: {os.getcwd()}")
         print("-" * 60)
    
    generator = RequirementsGenerator(project_directory)
    generator.run()
    generator.write_file()

    print("\n" + "=" * 60)
    print("💡 NEXT STEPS & BEST PRACTICES")
    print("1. Review the generated `requirements.txt` for any obvious errors.")
    print("2. For fully reproducible environments, it is recommended to use `pip-tools`.")
    print("   You can treat the generated file as a `requirements.in` and run:")
    print("   `pip-compile requirements.txt -o requirements.txt`")
    print("   This will pin all sub-dependencies, which is the industry best practice.")
    print("=" * 60)

if __name__ == "__main__":
    main()