"""Create GitHub Issues for Wave 4 Work Packages."""

import subprocess
from scaffold_wave4_plans import WAVE4_PLANS

def create_wave4_issues():
    for plan in WAVE4_PLANS:
        for wp in plan["wps"]:
            title = f"[{plan['slug']}] {wp['id']}: {wp['title']}"
            body_lines = [
                f"## Work Package {wp['id']}: {wp['title']}",
                "",
                f"**Plan**: [{plan['title']}](plans/{plan['dir']})",
                f"**Wave**: {plan['wave_name']}",
                f"**Target Branch**: `feat/{plan['slug']}`",
                "",
                "### Goal",
                wp["goal"],
                "",
                "### Target Files",
                f"`{wp['files']}`",
                "",
                "### Definition of Done",
                f"- [ ] {wp['dod']}",
                "- [ ] All tests passing with 0 errors.",
                "- [ ] Micro-branch PR targeting base branch reviewed and merged.",
            ]
            if wp.get("is_ui"):
                body_lines.extend([
                    "",
                    "### UI & Visual Standards",
                    "- [ ] Mandatory skills: `impeccable` and `huashu-design`.",
                    "- [ ] **No Emojis**: Emojis are strictly banned from UI copy, buttons, headers, cards, and navigation.",
                    "- [ ] **No Em Dashes**: Em dashes (`—`) are strictly banned from UI copy and labels.",
                    "- [ ] **Visual Assets**: Real photography, unDraw vector illustrations (`undraw.co`), or AI-generated images.",
                ])

            body = "\n".join(body_lines)
            cmd = [
                "gh", "issue", "create",
                "--title", title,
                "--body", body,
                "--milestone", plan["wave_name"],
                "--label", f"wave:{plan['wave']}",
                "--label", "type:work-package",
                "--label", plan["plan_label"],
            ]
            print(f"Creating issue: {title}")
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                issue_url = res.stdout.strip()
                print(f"  -> Created: {issue_url}")
            except subprocess.CalledProcessError as e:
                print(f"  Error creating issue for {wp['id']}: {e.stderr}")


if __name__ == "__main__":
    create_wave4_issues()
    print("Wave 4 GitHub issues creation complete!")
