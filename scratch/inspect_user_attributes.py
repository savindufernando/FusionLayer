import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.models import User
print("User attributes:")
print([attr for attr in dir(User) if not attr.startswith('_')])
