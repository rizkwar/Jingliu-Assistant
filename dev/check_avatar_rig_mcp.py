"""Exercise the real STDIO server on local rig copies, leaving a short report."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import struct
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from avatar_rig_data import RigStore


async def main():
    workspace = Path(__file__).resolve().parent.parent
    root = workspace/'.cache/avatar-authoring/jingliu'
    run = 'mcp-checks/' + uuid.uuid4().hex[:10]
    original = root/'authoring/jingliu-v5-import-v1.inx'
    source_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    checks = []
    params = StdioServerParameters(command=sys.executable, args=[str(workspace/'dev/avatar_rig_mcp.py'), '--root', str(root)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            assert len(listing.tools) == 14

            async def call(name, arguments=None, error=False):
                result = await session.call_tool(name, arguments or {})
                assert bool(result.isError) == error, (name, result)
                checks.append({'tool': name, 'expectedError': error, 'passed': True})
                if error:
                    return None
                return result.structuredContent or json.loads(next(c.text for c in result.content if c.type == 'text'))

            status = await call('rig_status')
            assert status['liveEditorControl'] is False
            await call('rig_list_files')
            rig = run+'/head-test.inx'
            await call('rig_build_jingliu', {'source': 'authoring/jingliu-v5-import-v1.inx', 'output': rig})
            info = await call('rig_inspect', {'file': rig})
            assert len(info['nodes']) == 24 and len(info['parameters']) == 3
            eye = next(n for n in info['nodes'] if n['name'] == 'Eye L - open')
            kwargs = {'file': rig, 'parameter': 'Head XY - small turn', 'node_uuid': eye['uuid'], 'x_index': 2, 'y_index': 1}
            key = await call('rig_get_keyform', {**kwargs, 'count': 2})
            offset = key['vertices'][0]['offset']
            edited = run+'/edited.inx'
            await call('rig_edit_keyform', {**kwargs, 'output': edited, 'edits': [{'index': 0, 'dx': offset[0]+.1, 'dy': offset[1]}]})
            pose = run+'/pose.inx'
            await call('rig_set_defaults', {'file': edited, 'output': pose, 'values': {'Head XY - small turn': [-.5, .5]}})
            await call('rig_validate', {'file': pose})
            preview = await call('rig_render_preview', {'file': pose, 'output': run+'/preview.png',
                                  'poses': [{'label':'Left','values':{'Head XY - small turn':[-1,0]}},
                                            {'label':'Right','values':{'Head XY - small turn':[1,0]}}], 'size':256})
            assert (root/preview['preview']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            torso=next(n for n in info['nodes'] if n['name']=='Torso and costume')
            replaced=run+'/texture-replaced.inx'
            await call('rig_replace_texture', {'file':rig,'output':replaced,'node_uuid':torso['uuid'],
                                              'png':'authoring/torso-clean-v3.png'})
            eyes=run+'/eyes.inx'
            built=await call('rig_build_jingliu_eyes',{'file':rig,'output':eyes,'manifest':'authoring/eye-parts-v4b.json'})
            assert built['parts']==29 and built['parameters']==6
            assert built['originalTextureSlotsPreserved']==23 and built['newTextureSlots']==10
            assert built['geometryChecks']['invertedTriangles']==0
            await call('rig_validate',{'file':eyes})
            await call('rig_render_preview',{'file':eyes,'output':run+'/eyes.png','size':256,'region':[420,505,420,190],
                'poses':[{'label':'Blink / opposite gaze','values':{'Eye L open':[0,0],'Eye gaze XY':[-1,1]}},
                         {'label':'Closed','values':{'Eye L open':[0,0],'Eye R open':[0,0]}}]})
            await call('rig_build_jingliu_eyes',{'file':rig,'output':run+'/bad-eyes.inx','manifest':'../outside.json'},error=True)
            mouth=run+'/mouth.inx'
            built_mouth=await call('rig_build_jingliu_mouth',{'file':eyes,'output':mouth,'manifest':'authoring/mouth-parts-v1.json'})
            assert built_mouth['parts']==34 and built_mouth['parameters']==8
            assert built_mouth['originalTextureSlotsPreserved']==33 and built_mouth['newTextureSlots']==5
            assert built_mouth['geometryChecks']['invertedTriangles']==0
            await call('rig_validate',{'file':mouth})
            await call('rig_render_preview',{'file':mouth,'output':run+'/mouth.png','size':256,'region':[420,505,420,310],
                'poses':[{'label':'Rounded / blink','values':{'Mouth open':[1,0],'Mouth form':[-1,0],'Eye L open':[0,0]}},
                         {'label':'Wide / head turn','values':{'Mouth open':[.5,0],'Mouth form':[1,0],'Head XY - small turn':[1,-1]}}]})
            for name,file,values in (('rest-before',eyes,{}),('rest-after',mouth,{}),('rest-form',mouth,{'Mouth form':[1,0]})):
                await call('rig_render_preview',{'file':file,'output':run+'/'+name+'.png','size':256,
                    'region':[420,505,420,310],'poses':[{'label':'Rest','values':values}]})
            assert (root/run/'rest-before.png').read_bytes()==(root/run/'rest-after.png').read_bytes()==(root/run/'rest-form.png').read_bytes()
            await call('rig_build_jingliu_mouth',{'file':eyes,'output':run+'/bad-mouth.inx','manifest':'../outside.json'},error=True)
            await call('rig_build_jingliu_mouth',{'file':eyes,'output':mouth,'manifest':'authoring/mouth-parts-v1.json'},error=True)
            idle=run+'/idle.inx'
            idle_result=await call('rig_add_idle_motion',{'file':mouth,'output':idle})
            assert idle_result['drawableParts']==34 and idle_result['physicsDrivers']==1
            assert len(idle_result['animations'])==3 and abs(idle_result['motionSamples']['hairEnd'])<1e-5
            info=await call('rig_inspect',{'file':idle})
            assert len(info['nodes'])==36 and len(info['parameters'])==8
            await call('rig_validate',{'file':idle})
            motion=await call('rig_render_motion_preview',{'file':idle,'output':run+'/idle.mp4','seconds':2,'fps':12,'size':256})
            assert (root/run/'idle.mp4').read_bytes()[4:8]==b'ftyp'
            assert motion['frames']==24 and motion['closedEyeFrames']>0
            await call('rig_render_motion_preview',{'file':idle,'output':'../escape.mp4'},error=True)
            await call('rig_render_motion_preview',{'file':idle,'output':run+'/idle.mp4'},error=True)
            await call('rig_render_motion_preview',{'file':idle,'output':run+'/unknown.mp4','animation':'Missing'},error=True)
            await call('rig_render_motion_preview',{'file':idle,'output':run+'/fast.mp4','fps':120},error=True)
            await call('rig_inspect', {'file': '../outside.inx'}, error=True)
            await call('rig_set_defaults', {'file': rig, 'output': rig, 'values': {'Head tilt': [.5, 0]}}, error=True)
            await call('rig_edit_keyform', {**kwargs, 'output': run+'/invalid.inx', 'edits': [{'index': -1, 'dx': 0, 'dy': 0}]}, error=True)
            store = RigStore(root)
            original_data, original_tail = store.read('authoring/jingliu-v5-import-v1.inx')
            data, tail = store.read(pose)
            assert tail == original_tail
            assert data['param'][0]['defaults'] == [-.5, .5]
            assert hashlib.sha256(original.read_bytes()).hexdigest() == source_hash
            _, replaced_tail=store.read(replaced)
            def blobs(section):
                count=struct.unpack_from('>I',section,8)[0];offset=12;result=[]
                for _ in range(count):
                    size=struct.unpack_from('>I',section,offset)[0]
                    result.append(section[offset:offset+size+5]);offset+=size+5
                return result
            before,after=blobs(tail),blobs(replaced_tail)
            assert len(before)==len(after)==23
            assert sum(a!=b for a,b in zip(before,after))==1
            eye_data,eye_tail=store.read(eyes)
            assert blobs(eye_tail)[:23]==before
            for side in ('L','R'):
                parts={n['name']:n for n in eye_data['nodes']['children']}
                iris=parts[f'Eye {side} - iris'];aperture=parts[f'Eye {side} - sclera aperture']
                assert iris['masks']==[{'source':aperture['uuid'],'mode':'Mask'}]
                parameter=next(p for p in eye_data['param'] if p['name']==f'Eye {side} open')
                alpha=next(b for b in parameter['bindings'] if b['node']==iris['uuid'] and b['param_name']=='opacity')
                assert alpha['values'][0]==[0] and alpha['values'][-1]==[1]
                assert not any(b['node']==iris['uuid'] and b['param_name']=='deform' for b in parameter['bindings'])
            mouth_data,mouth_tail=store.read(mouth)
            assert len(blobs(mouth_tail))==38 and blobs(mouth_tail)[:33]==blobs(eye_tail)
            nodes={n['uuid']:n for n in mouth_data['nodes']['children']}
            assert all(nodes[n['uuid']]==n for n in eye_data['nodes']['children'])
            assert all(b in next(p for p in mouth_data['param'] if p['uuid']==old['uuid'])['bindings']
                       for old in eye_data['param'] for b in old['bindings'])
            idle_data,idle_tail=store.read(idle)
            assert idle_tail==mouth_tail
            idle_nodes={n['uuid']:n for n in idle_data['nodes']['children']}
            assert all(idle_nodes[n['uuid']]==n for n in mouth_data['nodes']['children'])
            assert all(b in next(p for p in idle_data['param'] if p['uuid']==old['uuid'])['bindings']
                       for old in mouth_data['param'] for b in old['bindings'])
    report = {'transport': 'real MCP STDIO', 'tools': [t.name for t in listing.tools], 'checks': checks,
              'sourceUnchanged': True, 'embeddedArtworkUnchanged': True, 'pose': pose,
              'singleTextureReplacementVerified':True,'separatedEyeRigVerified':True,'separatedMouthRigVerified':True,
              'closedMouthRestPixelsPreserved':True,'idleTracksAndPhysicsVerified':True,
              'limitations': ['Not a live editor connection.', 'Previews use a limited software renderer.', 'Checks do not establish visual quality.']}
    report_path = root/run/'verification.json'
    report_path.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({'tools': len(listing.tools), 'checks': len(checks), 'sourceUnchanged': True,
                      'embeddedArtworkUnchanged': True, 'report': report_path.relative_to(workspace).as_posix()}, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
