// ytdexport: exports the textures of loose .ytd files to DDS (GTA V Legacy, or Enhanced/gen9 with --gen9).
// Usage: ytdexport <file.ytd | folder> <output> [--gen9]
// Writes <output>/<ytd name>/<texture>.dds and appends name, size and format to <output>/index.tsv.
using CodeWalker.GameFiles;
using CodeWalker.Utils;

if (args.Length < 2) { Console.Error.WriteLine("usage: ytdexport <ytd|folder> <output> [--gen9]"); return 1; }
RpfManager.IsGen9 = args.Contains("--gen9");
var input = args[0];
var outDir = args[1];
Directory.CreateDirectory(outDir);
var files = Directory.Exists(input) ? Directory.GetFiles(input, "*.ytd", SearchOption.AllDirectories) : new[] { input };
int ok = 0, fail = 0;
using var index = new StreamWriter(Path.Combine(outDir, "index.tsv"), append: true);
foreach (var f in files)
{
    var name = Path.GetFileNameWithoutExtension(f);
    try
    {
        var data = File.ReadAllBytes(f);
        var ytd = new YtdFile();
        ytd.Load(data);
        var texs = ytd.TextureDict?.Textures?.data_items;
        if (texs == null) { Console.Error.WriteLine($"{name}: no textures"); fail++; continue; }
        var dir = Path.Combine(outDir, name);
        Directory.CreateDirectory(dir);
        foreach (var t in texs)
        {
            try
            {
                var dds = DDSIO.GetDDSFile(t);
                var safe = string.Concat(t.Name.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '_' : c));
                File.WriteAllBytes(Path.Combine(dir, safe + ".dds"), dds);
                index.WriteLine($"{name}\t{t.Name}\t{t.Width}\t{t.Height}\t{t.Format}\t{t.Levels}");
                ok++;
            }
            catch (Exception e) { Console.Error.WriteLine($"{name}/{t.Name}: {e.Message}"); fail++; }
        }
    }
    catch (Exception e) { Console.Error.WriteLine($"{name}: {e.Message}"); fail++; }
}
Console.WriteLine($"textures exported: {ok}, failed: {fail}");
return 0;
