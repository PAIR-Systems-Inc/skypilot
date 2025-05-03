"""Utils for launching baseline load balancers."""

import argparse
import multiprocessing
import shlex
import subprocess
from typing import Any, Dict, List

from sky.lbbench import gen_cmd
from sky.lbbench import utils

enabled_systems = [i for i in gen_cmd.enabled_systems if i < 3]
describes = [gen_cmd.raw_describes[i] for i in enabled_systems]


def _prepare_sky_global_lb(st: Dict[str, Any], ct: List[Dict[str, Any]],
                           policy: str, cluster_name: str) -> str:
    ip = None
    for c in ct:
        if c['name'].startswith('sky-serve-controller'):
            ip = c['handle'].head_ip
            break
    if ip is None:
        raise ValueError('SkyServe controller not found')
    controller_port = st['controller_port']
    return (f'sky launch -c {cluster_name} -d --fast '
            '-y examples/serve/external-lb/global-sky-lb.yaml '
            f'--env IP={ip} --env PORT={controller_port} --env POLICY={policy}')


def _prepare_sgl_cmd(st: Dict[str, Any]) -> str:
    worker_urls = []
    for r in st['replica_info']:
        worker_urls.append(r['endpoint'])
    worker_urls_str = shlex.quote(' '.join(worker_urls))
    return (f'sky launch -c {utils.sgl_cluster} -d --fast '
            '-y examples/serve/external-lb/router.yaml '
            f'--env WORKER_URLS={worker_urls_str}')


def _run_cmd(cmd: str):
    print(f'Running command: {cmd}')
    subprocess.run(cmd, shell=True, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--service-names', type=str, nargs='+', required=True)
    args = parser.parse_args()
    sns = args.service_names
    if len(sns) != len(enabled_systems):
        raise ValueError(f'Expected {len(enabled_systems)} service names for '
                         f'{", ".join(describes)}')
    print(sns)
    all_st = utils.sky_serve_status()
    ct = utils.sky_status()
    sn2st = {s['name']: s for s in all_st}

    def _get_single_cmd(idx: int) -> str:
        idx_in_sns = enabled_systems.index(idx)
        if idx == 0:
            return _prepare_sgl_cmd(sn2st[sns[idx_in_sns]])
        elif idx == 1:
            # Global least load
            return _prepare_sky_global_lb(sn2st[sns[idx_in_sns]], ct, 'least_load',
                                          utils.global_least_load_cluster)
        elif idx == 2:
            # Sky SGL enhanced
            return _prepare_sky_global_lb(sn2st[sns[idx_in_sns]], ct, 'prefix_tree',
                                          utils.sky_sgl_enhanced_cluster)
        else:
            raise ValueError(f'Invalid index: {idx}')

    commands = [_get_single_cmd(i) for i in enabled_systems]
    for cmd in commands:
        print(cmd)
    input('Press Enter to launch LBs...')
    processes = []
    for cmd in commands:
        process = multiprocessing.Process(target=_run_cmd, args=(cmd,))
        processes.append(process)
        process.start()
    for process in processes:
        process.join()
    print('Both load balancers have been launched successfully. '
          'Check status with: \n'
          f'sky logs {utils.sgl_cluster}\n'
          f'sky logs {utils.global_least_load_cluster}\n'
          f'sky logs {utils.sky_sgl_enhanced_cluster}\n')


if __name__ == '__main__':
    # py -m sky.lbbench.launch_lb --service-names c11 c12 c13
    main()
