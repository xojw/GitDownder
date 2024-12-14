import os
import requests
import zipfile
import shutil
import json
from urllib.parse import urlparse
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

console = Console()

def save_token(token):
    with open("token.json", "w") as f:
        json.dump({"token": token}, f)

def load_token():
    if os.path.exists("token.json"):
        with open("token.json", "r") as f:
            data = json.load(f)
            return data.get("token")
    return None

def download_file(file_url, file_path, file_counter, headers):
    response = requests.get(file_url, headers=headers)
    response.raise_for_status()

    with open(file_path, 'wb') as f:
        f.write(response.content)
    console.log(f"[green][{file_counter}][/green] Downloaded: {file_path}")

def download_directory(api_url, save_path, file_counter, headers):
    response = requests.get(api_url, headers=headers)
    if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers and response.headers['X-RateLimit-Remaining'] == '0':
        raise Exception("Rate limit exceeded. Please provide a new token.")
    if response.status_code != 200:
        raise Exception(f"Failed to fetch directory data: {response.status_code} - {response.text}")

    os.makedirs(save_path, exist_ok=True)

    for item in response.json():
        file_path = os.path.join(save_path, item['name'])
        if item['type'] == 'file': 
            file_counter[0] += 1
            download_file(item['download_url'], file_path, file_counter[0], headers)
        elif item['type'] == 'dir': 
            console.log(f"[blue]Entering directory: {item['name']}[/blue]")
            download_directory(item['url'], file_path, file_counter, headers)

def zip_directory(source_dir, zip_file_name):
    file_count = 0
    with zipfile.ZipFile(zip_file_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, arcname)
                file_count += 1
                console.log(f"[yellow][{file_count}] Zipping: {arcname}[/yellow]")

    console.log(f"[green]Zipped {file_count} files into {zip_file_name}[/green]")
    return file_count

def parse_github_url(url):
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip('/').split('/')
    if len(path_parts) < 3 or path_parts[2] != 'tree':
        raise ValueError("Invalid GitHub subfolder URL. Ensure it points to a subfolder.")

    username = path_parts[0]
    repo = path_parts[1]
    branch = path_parts[3]
    subfolder_path = '/'.join(path_parts[4:])
    return username, repo, branch, subfolder_path

def ensure_zip_extension(filename):
    if not filename.lower().endswith('.zip'):
        filename += '.zip'
    return filename

def unzip_file(zip_file_path, extract_to_dir, progress):
    with zipfile.ZipFile(zip_file_path, 'r') as zipf:
        total_files = len(zipf.infolist())
        task = progress.add_task("Unzipping files", total=total_files)
        
        for file in zipf.infolist():
            zipf.extract(file, extract_to_dir)
            progress.update(task, advance=1)
            console.log(f"[yellow]Extracting: {file.filename}[/yellow]")

        console.log(f"[green]Unzipped the contents to {extract_to_dir}[/green]")

def main():
    console.rule("[bold cyan]GitDownder by Sefic")
    try:
        token = load_token()
        if not token:
            console.print(Panel("To avoid rate limits, please generate a GitHub token here: [blue underline]https://github.com/settings/tokens/new?description=Download%20GitHub%20directory&scopes=repo[/blue underline]", title="Token Required", style="bold red"))
            token = Prompt.ask("Enter your GitHub token").strip()
            save_token(token)

        headers = {"Authorization": f"token {token}"}

        github_url = Prompt.ask("Enter the GitHub subfolder URL").strip()

        downloads_dir = Path.home() / "Downloads"
        os.makedirs(downloads_dir, exist_ok=True)
        zip_file_name = Prompt.ask("Enter the name for the folder", default="github_download").strip()
        zip_file_name = ensure_zip_extension(zip_file_name) 
        zip_file_path = downloads_dir / zip_file_name

        username, repo, branch, subfolder_path = parse_github_url(github_url)
        api_url = f'https://api.github.com/repos/{username}/{repo}/contents/{subfolder_path}?ref={branch}'

        temp_dir = 'temp_download'
        file_counter = [0]

        console.print("\n[bold yellow]Starting download...[/bold yellow]")
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TimeRemainingColumn()) as progress:
            task = progress.add_task("Downloading files", total=None)
            download_directory(api_url, temp_dir, file_counter, headers)
            progress.update(task, completed=file_counter[0])
        console.print(f"\n[green]Downloaded {file_counter[0]} files.[/green]\n")

        console.print("[bold yellow]Starting zipping process...[/bold yellow]")
        total_zipped_files = zip_directory(temp_dir, zip_file_path)
        console.print(f"\n[bold green]Successfully zipped {total_zipped_files} files into {zip_file_path}.[/bold green]\n")

        unzip_dir = downloads_dir / zip_file_name.replace('.zip', '')
        os.makedirs(unzip_dir, exist_ok=True)

        console.print("[bold yellow]Starting unzipping process...[/bold yellow]")

        with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TimeRemainingColumn()) as progress:
            unzip_file(zip_file_path, unzip_dir, progress)

        os.remove(zip_file_path)
        console.log(f"[blue]Deleted ZIP file: {zip_file_path}[/blue]")

    except Exception as e:
        console.print(Panel(f"An error occurred: {e}", style="bold red"))
        if "Rate limit exceeded" in str(e):
            console.print("[bold yellow]Please generate a new token here: [blue underline]https://github.com/settings/tokens/new?description=Download%20GitHub%20directory&scopes=repo[/blue underline]")

            new_token = Prompt.ask("Enter your new GitHub token").strip()
            save_token(new_token)
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            console.print(f"[blue]Cleaned up temporary directory: {temp_dir}[/blue]")

        Prompt.ask("\nPress Enter to exit...")

if __name__ == '__main__':
    main()
