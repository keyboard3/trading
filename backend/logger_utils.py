class LogColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'  # Reset to default
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Example usage (can be removed or kept for testing this file directly):
if __name__ == '__main__':
    print(f"{LogColors.HEADER}This is a header.{LogColors.ENDC}")
    print(f"{LogColors.OKBLUE}This is ok blue.{LogColors.ENDC}")
    print(f"{LogColors.OKCYAN}This is ok cyan.{LogColors.ENDC}")
    print(f"{LogColors.OKGREEN}This is ok green (success).{LogColors.ENDC}")
    print(f"{LogColors.WARNING}This is a warning.{LogColors.ENDC}")
    print(f"{LogColors.FAIL}This is a failure (error).{LogColors.ENDC}")
    print(f"{LogColors.BOLD}This is bold.{LogColors.ENDC}")
    print(f"{LogColors.UNDERLINE}This is underlined.{LogColors.ENDC}")
    print(f"This is {LogColors.BOLD}{LogColors.FAIL}bold failure{LogColors.ENDC}!") 