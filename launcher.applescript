-- launcher.applescript — source for "Launch sf-initial-setup-agent.app".
--
-- Behavior:
--   1. If the agent is already running on 127.0.0.1:8765, just open the browser.
--   2. Otherwise, start ./run.sh in the background (no visible Terminal window)
--      with a sane PATH so prereqs (sf CLI, node, jq, etc.) resolve correctly.
--      The Python orchestrator picks a free port and opens the browser itself.
--
-- Build:
--   osacompile -o "Launch sf-initial-setup-agent.app" launcher.applescript
--
-- After building, the .app sits next to run.sh. We derive the parent folder
-- via `dirname` in a shell call rather than AppleScript's System Events /
-- Finder objects — those return folder references that don't coerce cleanly
-- into a POSIX path on every macOS version (got -1700 errAECoercionFail
-- testing against modern macOS in the agent's working tree).

on run
    -- POSIX path of the .app bundle itself, e.g.
    --   /Users/.../sf-initial-setup-agent/Launch sf-initial-setup-agent.app/
    set myPosix to POSIX path of (path to me)

    -- Strip trailing slash, then dirname to get the parent dir (= agent root).
    set parentPosix to do shell script "p=" & quoted form of myPosix & "; dirname \"${p%/}\""

    -- Health-check: is an agent already listening on the conventional port?
    set httpStatus to "0"
    try
        set httpStatus to do shell script "curl -fsS -o /dev/null -w '%{http_code}' --max-time 1 'http://127.0.0.1:8765/' 2>/dev/null || echo 0"
    end try
    if httpStatus is "200" then
        do shell script "open 'http://127.0.0.1:8765/'"
        return
    end if

    -- Boot the agent in the background. nohup + & detaches; PATH is widened
    -- because `do shell script` runs with a minimal env that may miss sf / node.
    set sh to "export PATH=\"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH\"; "
    set sh to sh & "cd " & quoted form of parentPosix & " && "
    set sh to sh & "nohup bash run.sh > /tmp/sf-initial-setup-agent.log 2>&1 &"
    do shell script sh
end run
