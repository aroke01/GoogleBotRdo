# Rig Update System Documentation

## Overview

The rig update system uses the `rdo_maya_rig_modelingupdater` package to query asset dependencies and determine if rigs are using the latest modeling versions.

## Script Location and Function

### Main Script
- **Package**: `rdo_maya_rig_modelingupdater`
- **Version**: 5.1.0 (latest)
- **Path**: `/rdo/software/rez/packages/rdo_maya_rig_modelingupdater/5.1.0/python/rdo_maya_rig_modelingupdater/core/_api.py`

### Function Called
- **Function**: `queryAssetDependencies(project, asset)`
- **Line**: 195 in `_api.py`
- **Module**: `rdo_maya_rig_modelingupdater.core`

## Usage Example

```python
import rdo_maya_rig_modelingupdater
import pprint

# Query asset dependencies for creTrummer in lbp3 project
data = rdo_maya_rig_modelingupdater.core.queryAssetDependencies('lbp3', 'creTrummer')
pprint.pprint(data)
```

## Expected Output Structure

The function returns a dictionary with rig variants as keys:

```python
{'rigVariant1': {'assetVariants': ['defVariant'],
                 'latestModeling': False,  # True if rig dependencies match latest modeling
                 'mocapRigVersions': ['creTrummer.cache.rigVariant1.all_v6'],
                 'modDependencies': ['creTrummer.hi.defVariant.body_v24',
                                     'creTrummer.hi.defVariant.tusk_v17'],
                 'rigDependencies': ['creTrummer.hi.defVariant.body_v23',
                                     'creTrummer.hi.defVariant.tusk_v16'],
                 'rigPublished': True,
                 'rigVersions': ['creTrummer.hi.rigVariant1.all_v20',
                                 'creTrummer.anim.rigVariant1.all_v20',
                                 'creTrummer.cache.rigVariant1.all_v20']},
 'rigVariant2': {'assetVariants': ['armor'],
                 'latestModeling': False,
                 'mocapRigVersions': ['creTrummer.cache.rigVariant2.all_v6'],
                 'modDependencies': ['creTrummer.hi.defVariant.body_v24',
                                     'creTrummer.hi.defVariant.tusk_v17',
                                     'creTrummer.hi.defVariant.armor_v7',
                                     'creTrummer.hi.defVariant.harness_v5'],
                 'rigDependencies': ['creTrummer.hi.defVariant.armor_v7',
                                     'creTrummer.hi.defVariant.body_v23',
                                     'creTrummer.hi.defVariant.harness_v5',
                                     'creTrummer.hi.defVariant.tusk_v16'],
                 'rigPublished': True,
                 'rigVersions': ['creTrummer.cache.rigVariant2.all_v17',
                                 'creTrummer.anim.rigVariant2.all_v17',
                                 'creTrummer.hi.rigVariant2.all_v17']},
 'rigVariant3': {'assetVariants': ['harness'],
                 'latestModeling': False,
                 'mocapRigVersions': ['creTrummer.cache.rigVariant3.all_v6'],
                 'modDependencies': ['creTrummer.hi.defVariant.body_v24',
                                     'creTrummer.hi.defVariant.tusk_v17',
                                     'creTrummer.hi.defVariant.harness_v5'],
                 'rigDependencies': ['creTrummer.hi.defVariant.body_v23',
                                     'creTrummer.hi.defVariant.harness_v5',
                                     'creTrummer.hi.defVariant.tusk_v16'],
                 'rigPublished': True,
                 'rigVersions': ['creTrummer.cache.rigVariant3.all_v10',
                                 'creTrummer.anim.rigVariant3.all_v10',
                                 'creTrummer.hi.rigVariant3.all_v10']}}
```

## Field Explanations

- **assetVariants**: List of modeling variants for this rig variant
- **latestModeling**: Boolean indicating if rig uses latest modeling versions
- **mocapRigVersions**: List of mocap rig version names
- **modDependencies**: Latest modeling version dependencies
- **rigDependencies**: Actual modeling versions used by the rig
- **rigPublished**: Boolean indicating if rig is published
- **rigVersions**: List of rig version names (cache, anim, hi)

## ShotGrid Integration

The system integrates with ShotGrid to show rig version status:

```
Rig Versions:
creTrummer_001 - v14 (OUTDATED, the latest approved version is v17)
prpNolmenStaff_001 - v1 (OUTDATED, the latest approved version is v3)
[Submitted via ARS: Caches will be created on approval of this daily.]
```

## Key Logic

The `latestModeling` field is determined by comparing:
- `modDependencies`: Latest available modeling versions
- `rigDependencies`: Actual modeling versions used in the rig

If these lists match (sorted), `latestModeling` is `True`; otherwise `False`.

## Dependencies

The function relies on:
- `rdo_context` for asset context
- `rdo_usd_utils.lib.assetDefinitionLib` for USD metadata
- `rdo_publish_pipeline.manager` for publish queries
- `rdo_rig_utils.constants` for LOD constants