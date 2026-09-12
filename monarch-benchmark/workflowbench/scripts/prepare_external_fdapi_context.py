"""Copy a reviewed, additive fdapi context. No deploy, source edits or DB writes."""
import argparse, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from wb_world.seeds import folder_sha256

def digest(path):
 return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory(root):
 root=Path(chr(92)*2+'?'+chr(92)+str(root)) if os.name=='nt' else root
 return {p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*')) if p.is_file()}

def git(root,*args):
 return subprocess.run(['git','-C',str(root),*args],capture_output=True,check=True).stdout

def prepare(source,out,packs):
 source=source.resolve();out=out.resolve()
 checkout=ROOT.parents[1].resolve()
 if out.is_relative_to(source) or out.is_relative_to(checkout): raise ValueError('Context must be outside both checkouts')
 if out.exists(): raise ValueError('Refusing to replace an existing context')
 dirty=git(source,'diff','--name-only').decode().strip()
 staged=git(source,'diff','--cached','--name-only').decode().strip()
 if dirty or staged: raise ValueError('Tracked Monarch source is dirty; review ownership before preparing')
 head=git(source,'rev-parse','HEAD').decode().strip()
 tracked=[Path(p.decode('utf-8')) for p in git(source,'ls-files','-z').split(b'\0') if p]
 fixture_rel=Path('feature-discovery/api/src/seeds/fixtures/public-api-seeds')
 fixtures=source/fixture_rel
 baseline=sorted(p for p in fixtures.glob('bench-*') if p.is_dir())
 if len(baseline)!=47 or sum(len(list(p.glob('*.json')))-int((p/'_meta.json').exists()) for p in baseline)!=686:
  raise ValueError('Current baseline is not the expected 47 products / 686 actions')
 baseline_files={str(p.relative_to(source).as_posix()):digest(p) for f in baseline for p in sorted(f.rglob('*')) if p.is_file()}
 staged_files={}
 pack_evidence=[]
 slugs={p.name for p in baseline}
 validator=source/'local-docs/benchmark/seed-format/validate-seeds.mjs'
 for pack in packs:
  pack=pack.resolve();meta=json.loads((pack/'ok.txt').read_text(encoding='utf-8'))
  if meta['sha256']!=folder_sha256(pack): raise ValueError('External pack digest mismatch')
  result=subprocess.run(['node',str(validator),str(pack),'--front-door',urlsplit(meta['front_door']).hostname,'--no-warn'],capture_output=True,text=True)
  if result.returncode: raise ValueError('Authoritative Monarch seed validation failed: '+result.stdout+result.stderr)
  expected=set(meta['service_slugs'].values());actual={p.name for p in pack.iterdir() if p.is_dir()}
  if actual!=expected: raise ValueError('Unmanifested source seed folder')
  if expected & slugs: raise ValueError('External product would replace an existing catalogue slug')
  slugs.update(expected)
  for name in sorted(expected):
   for p in sorted((pack/name).rglob('*')):
    if p.is_file(): staged_files[fixture_rel/name/p.relative_to(pack/name)]=p
  pack_evidence.append({'product':meta['product'],'source':meta['source'],'task_contracts':meta['task_contracts'],
     'products':meta['products'],'actions':meta['actions'],'service_slugs':meta['service_slugs'],
     'sha256':meta['sha256'],'pack_directory':str(pack),'authoritative_validator':result.stdout.strip()})
 all_sources={relative:source/relative for relative in tracked}
 all_sources.update({Path(relative):source/relative for relative in baseline_files})
 all_sources.update(staged_files)
 for relative,p in all_sources.items():
  if relative.is_absolute() or '..' in relative.parts or p.is_symlink(): raise ValueError('Unsafe build-context file path')
  if not p.is_file(): raise ValueError('Tracked file unavailable: '+str(relative))
 expected_hashes={relative.as_posix():digest(p) for relative,p in all_sources.items()}
 for relative,p in all_sources.items():
  target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2('\\\\?\\'+str(p),'\\\\?\\'+str(target))
 actual=inventory(out)
 if actual!=expected_hashes: raise ValueError('Copied context bytes differ from selected source files')
 if git(source,'rev-parse','HEAD').decode().strip()!=head or git(source,'diff','--name-only').strip() or git(source,'diff','--cached','--name-only').strip():
  raise ValueError('Tracked source changed while copying')
 baseline_after={relative:digest(source/relative) for relative in baseline_files}
 if baseline_after!=baseline_files: raise ValueError('Original baseline changed while copying')
 copied_baseline={relative:actual[relative] for relative in baseline_files}
 if copied_baseline!=baseline_files: raise ValueError('Copied baseline differs')
 h=hashlib.sha256()
 for relative,sha in sorted(actual.items()): h.update(relative.encode());h.update(bytes.fromhex(sha))
 manifest={'format':'workflowbench-additive-fdapi-context@1','source_directory':str(source),'source_commit':head,
   'source_tracked_clean':True,'context_directory':str(out),'tracked_files':len(tracked),'selected_file_count':len(actual),
   'selection':'Exactly tracked Monarch working-tree files + existing 47 bench seed directories + declared new seed directories; this manifest is the sole additional root file.',
   'baseline_products':47,'baseline_actions':686,'baseline_unchanged':True,'baseline_file_hashes':baseline_files,
   'external_packs':pack_evidence,'context_products':len(slugs),'context_actions':686+sum(p['actions'] for p in pack_evidence),
   'context_files_sha256':h.hexdigest(),'file_hashes':actual,
   'deployment_target':{'service':'fdapi','config':'infra/railway/services/fdapi.railway.json','dockerfile':'feature-discovery/api/Dockerfile'},
   'not_performed':['deployment','seed import','org product access mutation']}
 (out/'workflowbench-context-manifest.json').write_bytes((json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode())
 print(json.dumps({k:manifest[k] for k in ['context_directory','source_commit','tracked_files','selected_file_count','baseline_products','baseline_actions','baseline_unchanged','context_products','context_actions','context_files_sha256']}))
 return manifest

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=ROOT.parents[2]/'monarch');parser.add_argument('--out',type=Path,required=True);parser.add_argument('packs',type=Path,nargs='+')
 args=parser.parse_args();prepare(args.source,args.out,args.packs)
