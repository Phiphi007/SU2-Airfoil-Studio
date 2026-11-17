"""Import native 2-D SU2 meshes without moving or regenerating their nodes."""
from dataclasses import dataclass
from pathlib import Path
import json
import shutil
import numpy as np


@dataclass
class ImportedMesh:
    path: Path
    nodes: np.ndarray
    cells: list
    markers: dict
    stamp: tuple

    def wall(self, marker):
        if marker not in self.markers:
            raise ValueError(f'网格没有边界标记：{marker}')
        edges = self.markers[marker]
        neighbors = {}
        for first, second in edges:
            neighbors.setdefault(int(first), []).append(int(second))
            neighbors.setdefault(int(second), []).append(int(first))
        if any(len(adjacent) != 2 for adjacent in neighbors.values()):
            raise ValueError('所选翼型壁面必须构成一个闭合轮廓，不能有开口或分叉。')
        start = int(edges[0, 0]); ordered = [start]; previous = None; current = start
        for _ in range(len(neighbors)):
            nxt = next(node for node in neighbors[current] if node != previous)
            if nxt == start: break
            ordered.append(nxt); previous, current = current, nxt
        if len(ordered) != len(neighbors):
            raise ValueError('所选壁面包含多个不连通轮廓；当前翼型计算支持一个闭合壁面。')
        coordinates = self.nodes[ordered]
        # Selig-style start at the trailing edge, without changing any mesh node.
        trailing = int(np.argmax(coordinates[:, 0]))
        ordered = np.roll(np.array(ordered), -trailing)
        points = self.nodes[ordered]
        if len(points) < 3 or float(np.ptp(points[:, 0])) <= 0:
            raise ValueError('所选壁面没有有效的流向弦长。')
        area = np.sum(points[:, 0]*np.roll(points[:, 1],-1)-points[:, 1]*np.roll(points[:, 0],-1))
        if area < 0: ordered = np.r_[ordered[0], ordered[:0:-1]]
        ordered = np.r_[ordered, ordered[0]]
        return self.nodes[ordered], np.column_stack((ordered[:-1], ordered[1:]))


def read_mesh(path):
    path = Path(path).expanduser().resolve()
    before = path.stat()
    stamp = (before.st_size, before.st_mtime_ns)
    # Native ASCII exports may include comments and optional explicit node IDs.
    with path.open(encoding='utf-8-sig') as stream:
        def line():
            for raw in stream:
                value = raw.split('%',1)[0].split('#',1)[0].strip()
                if value: return value
            raise ValueError('SU2网格文件提前结束。')
        nodes = None; cells = []; markers = {}; dimension = None
        while True:
            try: item = line()
            except ValueError:
                if nodes is None or not markers: raise
                break
            if '=' not in item: raise ValueError(f'无法识别网格段：{item[:70]}')
            key, value = [part.strip() for part in item.split('=',1)]
            if key == 'NZONE' and value == '1':
                continue
            if key == 'NDIME':
                dimension = int(value)
                if dimension != 2: raise ValueError('当前翼型求解仅支持二维NDIME=2网格。')
            elif key == 'NELEM':
                for _ in range(int(value)):
                    parts = [int(v) for v in line().split()]
                    count = {5:3,9:4}.get(parts[0])
                    if count is None or len(parts)<count+1: raise ValueError('二维体单元仅支持三角形(5)和四边形(9)。')
                    cells.append((parts[0], np.array(parts[1:count+1],dtype=np.int64)))
            elif key == 'NPOIN':
                count = int(value.split()[0]); nodes = np.empty((count,2)); assigned=set()
                for index in range(count):
                    parts=line().split(); node=int(parts[2]) if len(parts)>2 else index
                    if node<0 or node>=count or node in assigned: raise ValueError('节点编号必须唯一且为0至NPOIN-1。')
                    assigned.add(node); nodes[node]=[float(parts[0]),float(parts[1])]
            elif key == 'NMARK':
                for _ in range(int(value)):
                    tag = line().split('=',1)
                    if tag[0].strip() != 'MARKER_TAG': raise ValueError('缺少MARKER_TAG。')
                    name=tag[1].strip()
                    if not name or name in markers or any(c in name for c in ',()\r\n'):
                        raise ValueError('边界名称为空、重复或含配置分隔字符。')
                    header=line().split('=',1)
                    if header[0].strip()!='MARKER_ELEMS': raise ValueError('缺少MARKER_ELEMS。')
                    boundary=[]
                    for _ in range(int(header[1])):
                        parts=[int(v) for v in line().split()]
                        if len(parts)!=3 or parts[0]!=3: raise ValueError('二维边界必须是线段单元(3)。')
                        boundary.append(parts[1:])
                    if not boundary: raise ValueError(f'边界{name}没有线段。')
                    markers[name]=np.asarray(boundary,dtype=np.int64)
            else:
                raise ValueError(f'当前不支持SU2网格段{key}（不支持多区或周期变换网格）。')
    if dimension!=2 or nodes is None or not cells or not markers or not np.isfinite(nodes).all():
        raise ValueError('网格缺少有效的二维节点、单元或边界。')
    all_edges = []
    for kind in (5, 9):
        connectivity = [ids for cell_kind, ids in cells if cell_kind == kind]
        if not connectivity:
            continue
        ids = np.asarray(connectivity)
        if ids.min() < 0 or ids.max() >= len(nodes) or np.any(np.diff(np.sort(ids,axis=1),axis=1)==0):
            raise ValueError('体单元节点索引越界或重复。')
        points = nodes[ids]
        cross = corner_metrics(points)[0]
        if np.any(~(np.all(cross>1e-12,axis=1) | np.all(cross<-1e-12,axis=1))):
            raise ValueError('网格存在退化、凹陷或交叉单元，请先修复网格。')
        all_edges.append(np.sort(np.stack((ids,np.roll(ids,-1,axis=1)),axis=-1).reshape(-1,2),axis=1))
    edge_ids, counts = np.unique(np.concatenate(all_edges),axis=0,return_counts=True)
    if np.any(counts>2):
        raise ValueError('网格存在非流形体单元连接。')
    exterior = set(map(tuple,edge_ids[counts==1].tolist()))
    boundary=set()
    for name,edges in markers.items():
        for a,b in edges:
            edge=tuple(sorted((int(a),int(b))))
            if edge not in exterior: raise ValueError(f'边界{name}含无效线段或非外边界。')
            if edge in boundary: raise ValueError('边界线段被多个标记重复指定。')
            boundary.add(edge)
    if boundary != exterior:
        raise ValueError('存在未分配边界标记的外边界，不能直接求解。')
    after = path.stat()
    if stamp != (after.st_size, after.st_mtime_ns):
        raise ValueError('读取期间网格文件发生更改，请重新导入。')
    return ImportedMesh(path,nodes,cells,markers,stamp)


BC_WIDTH={'MARKER_EULER':1,'MARKER_HEATFLUX':2,'MARKER_ISOTHERMAL':2,'MARKER_FAR':1,
          'MARKER_INLET':6,'MARKER_OUTLET':2,'MARKER_SUPERSONIC_INLET':6,
          'MARKER_SUPERSONIC_OUTLET':1,'MARKER_SYM':1,'MARKER_RIEMANN':7}


def boundary_config(mesh, wall_marker, farfield_markers, *, cfg='', wall_type='ADIABATIC', temperature=300., solver=None):
    if wall_marker not in mesh.markers: raise ValueError('请明确选择翼型壁面标记。')
    assignments={}; lines=[]
    if cfg:
        pending=''
        for raw in Path(cfg).read_text(encoding='utf-8-sig').splitlines():
            pending += ' '+raw.split('%',1)[0].strip()
            if pending.count('(')>pending.count(')'): continue
            if '=' not in pending: pending='';continue
            key,value=[v.strip() for v in pending.split('=',1)];pending=''
            if key in ('MARKER_MONITORING','MARKER_PLOTTING','MARKER_DESIGNING'):continue
            if key.startswith('MARKER_') and value.strip('() ').upper() == 'NONE':
                continue
            if key.startswith('MARKER_') and key not in BC_WIDTH:
                raise ValueError(f'暂不支持配套配置中的{key}，请使用受支持的二维边界。')
            if key in BC_WIDTH:
                tokens=[v.strip() for v in value.strip('() ').split(',')]
                width=BC_WIDTH[key]
                if len(tokens)%width: raise ValueError(f'{key}的参数数目不正确。')
                for name in tokens[::width]:
                    if name not in mesh.markers or name in assignments: raise ValueError(f'边界{name}不存在或被重复指定。')
                    assignments[name]=key
                lines.append(f'{key}= {value}')
            elif key in {'INLET_TYPE','RIEMANN_TYPE'}:lines.append(f'{key}= {value}')
        if pending.strip():raise ValueError('边界配置存在未闭合的定义。')
    else:
        far=[v.strip() for v in farfield_markers.split(',') if v.strip()]
        if len(far)!=len(set(far)) or wall_marker in far or set(far)|{wall_marker}!=set(mesh.markers):
            raise ValueError('每个边界必须恰好分配一次：选择一个翼型壁面，其余远场标记用逗号分隔；复杂边界请读入.cfg。')
        key={'SLIP':'MARKER_EULER','ADIABATIC':'MARKER_HEATFLUX','ISOTHERMAL':'MARKER_ISOTHERMAL'}[wall_type]
        value=wall_marker if key=='MARKER_EULER' else f'{wall_marker}, {0. if wall_type=="ADIABATIC" else temperature:.12g}'
        lines=[f'{key}= ( {value} )',f'MARKER_FAR= ( {", ".join(far)} )']
        assignments={wall_marker:key,**{name:'MARKER_FAR' for name in far}}
    if set(assignments)!=set(mesh.markers):raise ValueError('配套.cfg未覆盖全部网格边界。')
    wall_key = assignments[wall_marker]
    if wall_key not in {'MARKER_EULER','MARKER_HEATFLUX','MARKER_ISOTHERMAL'}:
        raise ValueError('所选翼型标记没有被指定为壁面。')
    if solver == 'EULER' and wall_key != 'MARKER_EULER':
        raise ValueError('Euler 求解需使用滑移壁面 MARKER_EULER。')
    if solver in {'RANS','NAVIER_STOKES'} and wall_key == 'MARKER_EULER':
        raise ValueError('黏性翼型求解需使用绝热或等温壁面。')
    return '\n'.join(lines+[f'MARKER_MONITORING= ( {wall_marker} )',f'MARKER_PLOTTING= ( {wall_marker} )'])


def corner_metrics(points):
    a = np.roll(points, 1, axis=1) - points
    b = np.roll(points, -1, axis=1) - points
    denominator = np.maximum(np.linalg.norm(a,axis=2)*np.linalg.norm(b,axis=2),np.finfo(float).tiny)
    cosine = np.sum(a*b,axis=2) / denominator
    sine = (a[:,:,0]*b[:,:,1] - a[:,:,1]*b[:,:,0]) / denominator
    return sine, np.degrees(np.arccos(np.clip(cosine,-1,1)))


def stage_mesh(mesh, output, wall_marker):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source = mesh.path.stat()
    if mesh.stamp != (source.st_size, source.st_mtime_ns):
        raise ValueError('网格文件已更改，请重新导入。')
    if mesh.path.resolve()!=(output/'mesh.su2').resolve():shutil.copy2(mesh.path,output/'mesh.su2')
    wall,edges=mesh.wall(wall_marker)
    preview=[];scores=[];angles=[];triangle_count=0
    for kind in (5,9):
        connectivity = [ids for cell_kind,ids in mesh.cells if cell_kind == kind]
        if not connectivity:
            continue
        ids = np.asarray(connectivity)
        sine, angle = corner_metrics(mesh.nodes[ids])
        scores.append(np.min(np.abs(sine),axis=1))
        angles.append(float(angle.min()))
        if kind == 5:
            triangle_count = len(ids)
            ids = np.column_stack((ids,ids[:,-1]))
        preview.append(ids)
    scores = np.concatenate(scores)
    q={'imported_mesh':True,'source_mesh':str(mesh.path),'quadrilateral_cells':len(mesh.cells)-triangle_count,
       'triangle_cells':triangle_count,'total_cells':len(mesh.cells),'total_nodes':len(mesh.nodes),
       'minimum_angle_deg':float(min(angles)),'minimum_scaled_jacobian':float(min(scores)),
       'markers':{name:len(edges) for name,edges in mesh.markers.items()},'wall_marker':wall_marker}
    np.savez_compressed(output/'mesh_preview.npz',nodes=mesh.nodes,quads=np.concatenate(preview),
                        wall_edges=edges,source_boundary=wall,cell_quality=scores)
    (output/'mesh_quality.json').write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf-8')
    np.savetxt(output/'processed_airfoil.dat',wall,header='Imported mesh wall: unchanged',comments='')
    return q
