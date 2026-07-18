#!/bin/zsh
set -euo pipefail

label="com.codex.ttft-proxy"
uid="$(id -u)"
domain="gui/${uid}"
root="$(cd "$(dirname "$0")" && pwd)"
plist="$HOME/Library/LaunchAgents/${label}.plist"
node="$(command -v node || true)"

if [[ -z "$node" ]]; then
  print -u2 'Node.js was not found in PATH. Install Node.js 24+ first.'
  exit 1
fi

create_plist() {
  mkdir -p "$HOME/Library/LaunchAgents"
  rm -f "$plist"
  /usr/libexec/PlistBuddy -c 'Clear dict' "$plist"
  /usr/libexec/PlistBuddy -c "Add :Label string $label" "$plist"
  /usr/libexec/PlistBuddy -c 'Add :ProgramArguments array' "$plist"
  /usr/libexec/PlistBuddy -c "Add :ProgramArguments:0 string $node" "$plist"
  /usr/libexec/PlistBuddy -c "Add :ProgramArguments:1 string $root/proxy.mjs" "$plist"
  /usr/libexec/PlistBuddy -c "Add :WorkingDirectory string $root" "$plist"
  /usr/libexec/PlistBuddy -c 'Add :EnvironmentVariables dict' "$plist"
  /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:TTFT_CONFIG_PATH string $root/proxy-config.json" "$plist"
  /usr/libexec/PlistBuddy -c 'Add :RunAtLoad bool true' "$plist"
  /usr/libexec/PlistBuddy -c 'Add :KeepAlive bool true' "$plist"
  /usr/libexec/PlistBuddy -c "Add :StandardOutPath string $root/proxy.log" "$plist"
  /usr/libexec/PlistBuddy -c "Add :StandardErrorPath string $root/proxy.error.log" "$plist"
}

case "${1:-install}" in
  install)
    create_plist
    launchctl bootout "$domain/$label" 2>/dev/null || true
    launchctl bootstrap "$domain" "$plist"
    launchctl kickstart -k "$domain/$label"
    print "Installed and started: $label"
    ;;
  uninstall)
    launchctl bootout "$domain/$label" 2>/dev/null || true
    rm -f "$plist"
    print "Removed: $label"
    ;;
  status)
    if [[ ! -f "$plist" ]]; then
      print "Not installed: $label"
      exit 1
    fi
    launchctl print "$domain/$label"
    ;;
  *)
    print -u2 "Usage: $0 {install|uninstall|status}"
    exit 2
    ;;
esac
