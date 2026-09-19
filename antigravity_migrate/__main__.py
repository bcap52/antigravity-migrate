"""
__main__.py - Entry point for python -m antigravity_migrate
"""

try:
    from .cli import main
except ImportError:
    from antigravity_migrate.cli import main

if __name__ == "__main__":
    main()
