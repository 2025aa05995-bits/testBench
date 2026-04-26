import re


class CommandParser:
    def parse(self, command: str):
        # Example: bench.ps.on True or bench.ps.setVoltage 12
        pattern = r"^(\w+)\.(\w+)\.(\w+)(?:\s+(.*))?$"
        match = re.match(pattern, command.strip())
        if not match:
            return None
        top, category, action, args = match.groups()
        args = args.split() if args else []
        return {
            'top': top,
            'category': category,
            'action': action,
            'args': args
        }


# Example usage
if __name__ == "__main__":
    parser = CommandParser()
    print(parser.parse("bench.ps.on True"))
    print(parser.parse("bench.ps.setVoltage 12"))
