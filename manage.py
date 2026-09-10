#!/usr/bin/env python
"""Django boshqaruv skripti — savdoyimbozor loyihasi."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django topilmadi. Virtual muhit yoqilganini va 'pip install -r "
            "requirements.txt' bajarilganini tekshiring."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
