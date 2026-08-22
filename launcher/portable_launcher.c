#include <windows.h>
#include <wchar.h>
#pragma comment(lib, "user32.lib")

static int fail(const wchar_t *message) {
    MessageBoxW(NULL, message, L"UA FREE Telegram Autopilot", MB_OK | MB_ICONERROR);
    return 1;
}

int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, PWSTR lpCmdLine, int nCmdShow) {
    (void)hInstance; (void)hPrevInstance; (void)lpCmdLine; (void)nCmdShow;

    wchar_t exePath[32768];
    DWORD len = GetModuleFileNameW(NULL, exePath, (DWORD)(sizeof(exePath) / sizeof(exePath[0])));
    if (len == 0 || len >= (DWORD)(sizeof(exePath) / sizeof(exePath[0]))) {
        return fail(L"Не вдалося визначити папку програми.");
    }

    wchar_t *slash = wcsrchr(exePath, L'\\');
    if (!slash) return fail(L"Некоректний шлях до програми.");
    *slash = L'\0';

    wchar_t pythonPath[32768];
    wchar_t appPath[32768];
    if (_snwprintf_s(pythonPath, 32768, _TRUNCATE, L"%s\\pythonw.exe", exePath) < 0 ||
        _snwprintf_s(appPath, 32768, _TRUNCATE, L"%s\\app.py", exePath) < 0) {
        return fail(L"Шлях до runtime занадто довгий.");
    }

    if (GetFileAttributesW(pythonPath) == INVALID_FILE_ATTRIBUTES) {
        return fail(L"У portable-збірці відсутній pythonw.exe.");
    }
    if (GetFileAttributesW(appPath) == INVALID_FILE_ATTRIBUTES) {
        return fail(L"У portable-збірці відсутній app.py.");
    }
    if (!SetCurrentDirectoryW(exePath)) {
        return fail(L"Не вдалося відкрити робочу папку програми.");
    }

    wchar_t commandLine[65536];
    if (_snwprintf_s(commandLine, 65536, _TRUNCATE, L"\"%s\" \"%s\"", pythonPath, appPath) < 0) {
        return fail(L"Не вдалося сформувати команду запуску.");
    }

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    ZeroMemory(&pi, sizeof(pi));
    si.cb = sizeof(si);

    if (!CreateProcessW(
            pythonPath,
            commandLine,
            NULL,
            NULL,
            FALSE,
            0,
            NULL,
            exePath,
            &si,
            &pi)) {
        wchar_t msg[512];
        _snwprintf_s(msg, 512, _TRUNCATE, L"Не вдалося запустити runtime. Windows error: %lu", GetLastError());
        return fail(msg);
    }

    CloseHandle(pi.hThread);
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD exitCode = 1;
    GetExitCodeProcess(pi.hProcess, &exitCode);
    CloseHandle(pi.hProcess);
    return (int)exitCode;
}
