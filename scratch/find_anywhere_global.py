import os

for root, dirs, files in os.walk("."):
    # Skip large directories
    if any(k in root for k in [".git", "node_modules", ".next", "build", ".gradle", ".idea"]):
        continue
    for file in files:
        if file.endswith((".dart", ".py", ".ts", ".tsx", ".js", ".jsx", ".html", ".css", ".json")):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Check for "SELECTED:" case-insensitive
                if "selected:" in content.lower():
                    for i, line in enumerate(content.splitlines()):
                        if "selected:" in line.lower() and ("6." in line or "79." in line or "lat" in line.lower() or "lon" in line.lower() or "text" in line.lower() or "warning" in line.lower()):
                            print(f"{filepath} (Line {i+1}): {line.strip()}")
            except Exception as e:
                pass
