# Sets or reads a shortcut's AppUserModelID, so Windows groups the running window with the
# pinned/Start Menu shortcut (one taskbar icon) instead of showing a second one.
# The app sets the same ID for its process: companion/launcher.py (APP_ID).

$AppId = 'Jingliu.DesktopCompanion'

if (-not ('ShortcutAppId' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IShortcutPropertyStore {
    [PreserveSig] int GetCount(out uint count);
    [PreserveSig] int GetAt(uint index, out ShortcutPropertyKey key);
    [PreserveSig] int GetValue(ref ShortcutPropertyKey key, out ShortcutPropVariant value);
    [PreserveSig] int SetValue(ref ShortcutPropertyKey key, ref ShortcutPropVariant value);
    [PreserveSig] int Commit();
}

[StructLayout(LayoutKind.Sequential, Pack = 4)]
public struct ShortcutPropertyKey { public Guid FormatId; public uint PropertyId; }

[StructLayout(LayoutKind.Explicit, Size = 16)]
public struct ShortcutPropVariant {
    [FieldOffset(0)] public ushort Type;
    [FieldOffset(8)] public IntPtr Pointer;
}

public static class ShortcutAppId {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHGetPropertyStoreFromParsingName(string path, IntPtr context, int flags, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IShortcutPropertyStore store);

    static ShortcutPropertyKey Key() {
        // PKEY_AppUserModel_ID
        return new ShortcutPropertyKey { FormatId = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), PropertyId = 5 };
    }

    static IShortcutPropertyStore Open(string path, int flags) {
        Guid iid = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99");
        IShortcutPropertyStore store;
        SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, flags, ref iid, out store);
        return store;
    }

    public static void Set(string path, string id) {
        IShortcutPropertyStore store = Open(path, 2);  // GPS_READWRITE
        ShortcutPropertyKey key = Key();
        ShortcutPropVariant value = new ShortcutPropVariant { Type = 31, Pointer = Marshal.StringToCoTaskMemUni(id) };  // VT_LPWSTR
        try {
            Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value));
            Marshal.ThrowExceptionForHR(store.Commit());
        } finally {
            Marshal.FreeCoTaskMem(value.Pointer);
            Marshal.ReleaseComObject(store);
        }
    }
}
'@
}

function Set-ShortcutAppId([string]$Path) { [ShortcutAppId]::Set($Path, $AppId) }
function Get-ShortcutAppId([string]$Path) {
    $folder = (New-Object -ComObject Shell.Application).NameSpace((Split-Path $Path))
    $folder.ParseName((Split-Path $Path -Leaf)).ExtendedProperty('System.AppUserModel.ID')
}
