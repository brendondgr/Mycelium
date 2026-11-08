"""The delivery tool's models, taken over from the content app.

State only: the tables already exist (created by the content migrations, kept
under their names by each model's Meta.db_table and each ManyToManyField's
db_table); this migration only tells Django the models now belong here. The
content types are re-homed so existing permissions follow the models.
"""

import uuid

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import tools.delivery.models

MOVED = ('announcement', 'announcementnudge', 'announcementpost', 'announcementreaction', 'announcementsettings', 'closingsoonpost', 'collection', 'collectionitem', 'dailybriefing', 'ignoreditem', 'labreminderpolicy', 'membersuggestion', 'notification', 'projectalert', 'projectitemseen', 'projectshare', 'reflectionproposal', 'reminderfire', 'remindermention', 'reminderoffset', 'remindersubscription', 'savedopportunity',)


def move_content_types(apps, schema_editor):
    """Re-home the moved models' content types (and so their permissions)."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    for model in MOVED:
        if not ContentType.objects.filter(app_label='delivery', model=model).exists():
            ContentType.objects.filter(app_label='content', model=model).update(
                app_label='delivery'
            )


def restore_content_types(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    for model in MOVED:
        if not ContentType.objects.filter(app_label='content', model=model).exists():
            ContentType.objects.filter(app_label='delivery', model=model).update(
                app_label='content'
            )


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('accounts', '0032_org_limit_overrides'),
        ('content', '0039_hand_off_delivery_models'),
        ('integrations', '0014_guest_reminders'),
        ('research', '0006_project_aliases'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # State only: the tables keep their names and their rows (each moved
        # model pins Meta.db_table), so the database is not touched.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Announcement',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('snapshot', models.JSONField(blank=True, default=dict)),
                        ('category', models.CharField(max_length=20)),
                        ('origin', models.CharField(choices=[('nightly', 'Nightly'), ('manual', 'Manual')], default='nightly', max_length=16)),
                        ('state', models.CharField(choices=[('posted', 'Posted'), ('skipped', 'Held back'), ('seeded_seen', 'Passed over at activation'), ('closed', 'Closed')], max_length=16)),
                        ('label', models.CharField(blank=True, choices=[('new_call', 'New call'), ('newly_relevant', 'Newly relevant'), ('already_open', 'Already open')], max_length=16)),
                        ('skip_reason', models.CharField(blank=True, default='', max_length=300)),
                        ('dept_reasons', models.JSONField(blank=True, default=list)),
                        ('checks', models.JSONField(blank=True, default=list)),
                        ('alignment', models.JSONField(blank=True, default=dict)),
                        ('write_up', models.JSONField(blank=True, default=dict)),
                        ('write_up_key', models.CharField(blank=True, default='', max_length=64)),
                        ('facts', models.JSONField(blank=True, default=dict)),
                        ('facts_fingerprint', models.CharField(blank=True, default='', max_length=64)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('closed_at', models.DateTimeField(blank=True, null=True)),
                        ('content', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='announcements', to='content.contentitem')),
                        ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('target_department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='announcements', to='accounts.department')),
                        ('target_lab', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='announcements', to='accounts.lab')),
                    ],
                    options={
                        'db_table': 'content_announcement',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='AnnouncementNudge',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('discord_user_id', models.CharField(blank=True, default='', max_length=32)),
                        ('offset', models.CharField(choices=[('none', 'No reminder'), ('2d', '2 days before'), ('1w', '1 week before'), ('2w', '2 weeks before'), ('3w', '3 weeks before'), ('1m', '1 month before'), ('2m', '2 months before')], max_length=4)),
                        ('source', models.CharField(choices=[('interested', 'Interested (default nudge)'), ('remind', 'Remind me')], max_length=16)),
                        ('delivery', models.CharField(choices=[('thread', 'Tag in the thread'), ('dm', 'Direct message')], default='thread', max_length=8)),
                        ('active', models.BooleanField(default=True)),
                        ('fired_for', models.JSONField(blank=True, default=list)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('announcement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='nudges', to='delivery.announcement')),
                        ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='announcement_nudges', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_announcementnudge',
                    },
                ),
                migrations.CreateModel(
                    name='AnnouncementPost',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('channel_id', models.CharField(max_length=32)),
                        ('thread_id', models.CharField(blank=True, default='', max_length=32)),
                        ('thread_name', models.CharField(blank=True, default='', max_length=100)),
                        ('outbox_key', models.CharField(blank=True, default='', max_length=200)),
                        ('update_log', models.JSONField(blank=True, default=list)),
                        ('posted_at', models.DateTimeField(blank=True, null=True)),
                        ('closed_at', models.DateTimeField(blank=True, null=True)),
                        ('deleted_at', models.DateTimeField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('announcement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='posts', to='delivery.announcement')),
                        ('binding', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='announcement_posts', to='integrations.discordtargetbinding')),
                    ],
                    options={
                        'db_table': 'content_announcementpost',
                    },
                ),
                migrations.CreateModel(
                    name='AnnouncementReaction',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('kind', models.CharField(choices=[('interested', 'Interested'), ('unfollow', 'Stopped following'), ('not_for_us', 'Not for us'), ('remind', 'Remind me'), ('link_click', 'Opened the thread from the web')], max_length=16)),
                        ('reason', models.CharField(blank=True, default='', max_length=500)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('announcement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reactions', to='delivery.announcement')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='announcement_reactions', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_announcementreaction',
                        'ordering': ['created_at', 'id'],
                    },
                ),
                migrations.CreateModel(
                    name='AnnouncementSettings',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('enabled', models.BooleanField(default=False)),
                        ('grants', models.BooleanField(default=True)),
                        ('fellowships', models.BooleanField(default=True)),
                        ('conferences', models.BooleanField(default=True)),
                        ('daily_cap', models.IntegerField(default=-1, help_text='-1 means no limit.')),
                        ('default_nudge', models.CharField(choices=[('none', 'No reminder'), ('2d', '2 days before'), ('1w', '1 week before'), ('2w', '2 weeks before'), ('3w', '3 weeks before'), ('1m', '1 month before'), ('2m', '2 months before')], default='2w', max_length=4)),
                        ('closing_soon_list', models.BooleanField(default=True)),
                        ('strong_match_tagging', models.BooleanField(default=False)),
                        ('save_on_interest', models.BooleanField(default=True)),
                        ('activation_seed', models.PositiveSmallIntegerField(default=6)),
                        ('min_award', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                        ('activated_at', models.DateTimeField(blank=True, null=True)),
                        ('seeded_at', models.DateTimeField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('target_department', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='announcement_settings', to='accounts.department')),
                        ('target_lab', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='announcement_settings', to='accounts.lab')),
                        ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_announcementsettings',
                    },
                ),
                migrations.CreateModel(
                    name='ClosingSoonPost',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('category', models.CharField(max_length=20)),
                        ('on_date', models.DateField()),
                        ('outbox_key', models.CharField(max_length=200)),
                        ('thread_id', models.CharField(blank=True, default='', max_length=32)),
                        ('replaced_at', models.DateTimeField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('binding', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='closing_soon_posts', to='integrations.discordtargetbinding')),
                    ],
                    options={
                        'db_table': 'content_closingsoonpost',
                        'ordering': ['-on_date'],
                    },
                ),
                migrations.CreateModel(
                    name='Collection',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('name', models.CharField(max_length=200)),
                        ('description', models.TextField(blank=True, default='')),
                        ('is_archived', models.BooleanField(default=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_collections', to=settings.AUTH_USER_MODEL)),
                        ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='collections', to='research.project')),
                    ],
                    options={
                        'db_table': 'content_collection',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='CollectionItem',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('note', models.TextField(blank=True, default='')),
                        ('added_at', models.DateTimeField(auto_now_add=True)),
                        ('added_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='added_collection_items', to=settings.AUTH_USER_MODEL)),
                        ('collection', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='delivery.collection')),
                        ('content', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='collection_items', to='content.contentitem')),
                    ],
                    options={
                        'db_table': 'content_collectionitem',
                        'ordering': ['-added_at'],
                    },
                ),
                migrations.CreateModel(
                    name='DailyBriefing',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('body', models.TextField(blank=True, default='', help_text="The 2–3 paragraph briefing prose (Mylo's voice).")),
                        ('origin', models.CharField(choices=[('llm', 'LLM'), ('fallback', 'Fallback'), ('carried', 'Carried forward')], default='fallback', help_text='Whether the LLM wrote the body, the deterministic fallback did, or it was carried forward from the previous day (nothing new to say).', max_length=20)),
                        ('categories', models.JSONField(blank=True, default=list, help_text='Snapshot of the watched categories this briefing covered.')),
                        ('counts', models.JSONField(blank=True, default=dict, help_text="Per-category item counts, e.g. {'papers': 12, 'grants': 3}.")),
                        ('new_counts', models.JSONField(blank=True, default=dict, help_text="Per-category counts of items that entered the target's Top-25 on this run — what the briefing leads with; counts keeps the total matched.")),
                        ('showcase', models.JSONField(blank=True, default=dict, help_text='Top items per category the briefing references (grounding).')),
                        ('project_summary', models.JSONField(blank=True, default=list, help_text="The report's summary table: one row per part (Personal first, then each project), each carrying the count of items that entered that part's Top-25 per category. Empty on briefings written before the table existed.")),
                        ('narrative', models.JSONField(blank=True, default=dict, help_text="Mylo's prose as structure rather than markdown: {'lead', 'lead_origin', 'themes': [{'cluster_id', 'label', 'read', 'origin'}]}. Stored once per run and read back by the PDF, the app, and the Discord message, so the three can never carry different wordings of the same day — and so a re-render never re-bills the model for prose that already exists.")),
                        ('kind', models.CharField(choices=[('daily', 'Daily'), ('weekly', 'Weekly')], db_index=True, default='daily', help_text='Daily or weekly. Every existing reader keeps reading dailies.', max_length=20)),
                        ('stats', models.JSONField(blank=True, default=dict, help_text="The run's statistics as structure — overnight volume, what matched, what entered, the per-category / per-project / per-theme splits, alerts and the deadline horizon. Stored so the web header and the Discord post show identical numbers rather than each deriving their own from the same rows at two different moments.")),
                        ('verification', models.JSONField(blank=True, default=dict, help_text="The citation verifier's record for a weekly: claims checked, supported, removed, and the sentences it removed with the check that failed. Empty on a daily, which cites nothing the model wrote without a packet behind it.")),
                        ('context_version', models.CharField(blank=True, default='', help_text='A digest of what the report was written against: the declared profile, the understanding the person confirmed, and the project developments in effect (ambient Plan 05). Two reports with the same version were written against the same picture of the reader; an old report stays interpretable because its version is known.', max_length=64)),
                        ('generated_on', models.DateField(db_index=True, default=django.utils.timezone.localdate, help_text='The local date this briefing covers — the history key.')),
                        ('generated_at', models.DateTimeField(auto_now=True, help_text='When this briefing was last (re)generated.')),
                        ('lab', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='daily_briefings', to='accounts.lab')),
                        ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='daily_briefings', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_dailybriefing',
                        'ordering': ['-generated_on', '-generated_at'],
                    },
                ),
                migrations.CreateModel(
                    name='IgnoredItem',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('area', models.CharField(choices=[('grant', 'Grant'), ('conference', 'Conference'), ('fellowship', 'Fellowship'), ('paper', 'Paper')], help_text='Which feed the item was ignored from (mirrors the save areas).', max_length=20)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('content', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ignores', to='content.contentitem')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ignored_items', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_ignoreditem',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='LabReminderPolicy',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('default_offsets', models.JSONField(blank=True, default=tools.delivery.models.default_reminder_offsets)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('default_mentions', models.ManyToManyField(blank=True, db_table='content_labreminderpolicy_default_mentions', related_name='reminder_policy_defaults', to=settings.AUTH_USER_MODEL)),
                        ('lab', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='reminder_policy', to='accounts.lab')),
                    ],
                    options={
                        'db_table': 'content_labreminderpolicy',
                    },
                ),
                migrations.CreateModel(
                    name='Notification',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('kind', models.CharField(choices=[('reminder', 'Reminder'), ('deadline_moved', 'Deadline moved'), ('high_signal', 'High signal'), ('project_alert', 'Project alert'), ('delivery_failed', 'Delivery failed'), ('collab_renewal', 'Collaboration setting ending'), ('suggestion_pending', 'Mylo has a question'), ('change_applied', 'A change you confirmed took effect'), ('change_undone', 'A change was undone')], max_length=20)),
                        ('title', models.CharField(max_length=500)),
                        ('body', models.TextField(blank=True, default='')),
                        ('url', models.URLField(blank=True, default='', max_length=500)),
                        ('dedupe_key', models.CharField(max_length=200, unique=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('read_at', models.DateTimeField(blank=True, null=True)),
                        ('dismissed_at', models.DateTimeField(blank=True, null=True)),
                        ('content', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notifications', to='content.contentitem')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_notification',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='ProjectAlert',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('trigger', models.CharField(choices=[('overlap_risk', 'Overlap risk'), ('unblocks', 'Unblocks'), ('timeline', 'Fits your timeline'), ('deadline_moved', 'Deadline moved'), ('team_gap', 'Team gap')], db_index=True, max_length=20)),
                        ('fired_on', models.DateField(db_index=True, default=django.utils.timezone.localdate)),
                        ('evidence', models.JSONField(blank=True, default=dict, help_text='What the matcher computed — similarities, the blocker it matched, the timeline row, the requirement nobody covers. The model writes prose *from* this and may not add a number to it.')),
                        ('delivered_in', models.JSONField(blank=True, default=list, help_text="Surfaces this alert has already reached, e.g. ['web:2026-09-16'].")),
                        ('status', models.CharField(choices=[('open', 'Open'), ('held', 'Held for the weekly'), ('acted', 'Acted on'), ('dismissed', 'Dismissed')], db_index=True, default='open', max_length=20)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('content', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project_alerts', to='content.contentitem')),
                        ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alerts', to='research.project')),
                        ('target_lab', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='project_alerts', to='accounts.lab')),
                        ('target_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='project_alerts', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_projectalert',
                        'ordering': ['-fired_on', '-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='ProjectItemSeen',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('first_seen_at', models.DateTimeField(auto_now_add=True)),
                        ('first_seen_via', models.CharField(choices=[('digest', 'Digest'), ('share', 'Share'), ('external_link', 'External link')], max_length=20)),
                        ('content', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project_seen', to='content.contentitem')),
                        ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='seen_items', to='research.project')),
                        ('seen_by', models.ManyToManyField(blank=True, db_table='content_projectitemseen_seen_by', help_text='Members who have actually viewed the item in-app.', related_name='project_items_seen', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_projectitemseen',
                    },
                ),
                migrations.CreateModel(
                    name='ProjectShare',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('note', models.TextField(blank=True, default='', help_text="The sharer's one-line why.")),
                        ('source', models.CharField(choices=[('digest', 'Digest'), ('external_link', 'External link'), ('collection', 'Collection')], default='digest', max_length=20)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('content', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project_shares', to='content.contentitem')),
                        ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shares', to='research.project')),
                        ('shared_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project_shares', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_projectshare',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='MemberSuggestion',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('score', models.FloatField(help_text='Normalized cosine, member profile vs item.')),
                        ('suggested', models.BooleanField(help_text='True = delivered; False = below-floor abstention, persisted for audit.')),
                        ('floor_used', models.FloatField(help_text='The cosine floor applied at decision time.')),
                        ('delivered_via', models.CharField(blank=True, default='', max_length=20)),
                        ('dismissed', models.BooleanField(default=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('content', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='member_suggestions', to='content.contentitem')),
                        ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='member_suggestions', to='research.project')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='member_suggestions', to=settings.AUTH_USER_MODEL)),
                        ('origin_share', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='suggestions', to='delivery.projectshare')),
                    ],
                    options={
                        'db_table': 'content_membersuggestion',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='ReflectionProposal',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('kind', models.CharField(choices=[('add_method', 'Add a method'), ('add_exclusion', 'Add an exclusion'), ('set_milestone', 'Set a milestone'), ('review_state', 'Review the state'), ('close_blocker', 'Close a blocker'), ('drop_method', 'Drop a method')], max_length=20)),
                        ('proposal', models.JSONField(blank=True, default=dict, help_text='The change itself, in the shape a state PATCH would take.')),
                        ('evidence', models.JSONField(blank=True, default=dict, help_text='What the reader did that produced it — counts, the shared term.')),
                        ('status', models.CharField(choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected'), ('expired', 'Expired')], db_index=True, default='pending', max_length=20)),
                        ('expires_on', models.DateField(db_index=True)),
                        ('decided_at', models.DateTimeField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reflection_proposals', to='research.project')),
                        ('target_lab', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='reflection_proposals', to='accounts.lab')),
                        ('target_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='reflection_proposals', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_reflectionproposal',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='ReminderSubscription',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('deadline_kind', models.CharField(choices=[('application', 'Application'), ('abstract', 'Abstract'), ('manuscript', 'Manuscript'), ('event', 'Event'), ('other', 'Other')], max_length=20)),
                        ('deadline_round_key', models.CharField(blank=True, default='', help_text='Which round of that kind this reminder is for — the matching ContentDeadline.round_key. Empty for a single-round deadline.', max_length=160)),
                        ('area', models.CharField(choices=[('grant', 'Grant'), ('conference', 'Conference'), ('fellowship', 'Fellowship'), ('paper', 'Paper')], max_length=20)),
                        ('title', models.CharField(max_length=500)),
                        ('round_label', models.CharField(blank=True, default='', help_text="Snapshot of the round's wording, so a fired message can name it.", max_length=200)),
                        ('url', models.URLField(blank=True, default='', max_length=500)),
                        ('due_date', models.DateField(blank=True, null=True)),
                        ('confidence', models.CharField(choices=[('confirmed', 'Confirmed'), ('anticipated', 'Anticipated'), ('rolling', 'Rolling'), ('unknown', 'Unknown')], default='confirmed', max_length=20)),
                        ('channel_id_override', models.CharField(blank=True, default='', help_text='Lab only: a specific channel instead of the lab default.', max_length=32)),
                        ('snoozed_until', models.DateField(blank=True, null=True)),
                        ('has_unlinked_targets', models.BooleanField(default=False, help_text='A mention target has no active Discord identity (portal prompts).')),
                        ('state', models.CharField(choices=[('active', 'Active'), ('fired_out', 'Fired out'), ('cancelled', 'Cancelled'), ('stale', 'Stale')], default='active', max_length=20)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('content', models.ForeignKey(blank=True, help_text='Live item; nulled when pruned — the snapshot then drives the tick.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reminders', to='content.contentitem')),
                        ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_reminders', to=settings.AUTH_USER_MODEL)),
                        ('target_lab', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='reminders', to='accounts.lab')),
                        ('target_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='reminders', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_remindersubscription',
                        'ordering': ['due_date', 'created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='ReminderOffset',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('amount', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                        ('unit', models.CharField(choices=[('day', 'Day'), ('week', 'Week'), ('month', 'Month'), ('year', 'Year')], max_length=10)),
                        ('subscription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offsets', to='delivery.remindersubscription')),
                    ],
                    options={
                        'db_table': 'content_reminderoffset',
                    },
                ),
                migrations.CreateModel(
                    name='ReminderMention',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('kind', models.CharField(choices=[('user', 'User'), ('role', 'Role'), ('everyone', 'Everyone')], default='user', max_length=10)),
                        ('discord_id', models.CharField(blank=True, default='', help_text='Guild member or role snowflake; empty for an @everyone mention.', max_length=32)),
                        ('display_name', models.CharField(blank=True, default='', help_text='What to show in the portal for a target with no Mycelium user.', max_length=120)),
                        ('member', models.ForeignKey(blank=True, help_text='Set only when the target is a linked Mycelium user.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='reminder_mentions', to=settings.AUTH_USER_MODEL)),
                        ('subscription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions', to='delivery.remindersubscription')),
                    ],
                    options={
                        'db_table': 'content_remindermention',
                    },
                ),
                migrations.CreateModel(
                    name='ReminderFire',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('idempotency_key', models.CharField(max_length=200, unique=True)),
                        ('fired_on', models.DateField(db_index=True)),
                        ('days_remaining', models.IntegerField(blank=True, null=True)),
                        ('channel', models.CharField(choices=[('in_app', 'In-app'), ('discord_dm', 'Discord DM'), ('discord_channel', 'Discord channel')], max_length=20)),
                        ('state', models.CharField(choices=[('sent', 'Sent'), ('queued', 'Queued'), ('skipped', 'Skipped'), ('failed', 'Failed')], max_length=20)),
                        ('skip_reason', models.CharField(blank=True, default='', max_length=40)),
                        ('outbox_key', models.CharField(blank=True, default='', max_length=200)),
                        ('discord_message_id', models.CharField(blank=True, default='', max_length=32)),
                        ('attempts', models.PositiveSmallIntegerField(default=0)),
                        ('error_code', models.IntegerField(blank=True, null=True)),
                        ('sent_at', models.DateTimeField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('subscription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fires', to='delivery.remindersubscription')),
                    ],
                    options={
                        'db_table': 'content_reminderfire',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='SavedOpportunity',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('area', models.CharField(choices=[('grant', 'Grant'), ('conference', 'Conference'), ('fellowship', 'Fellowship'), ('paper', 'Paper')], max_length=20)),
                        ('title', models.CharField(help_text='Snapshot at save time.', max_length=500)),
                        ('url', models.URLField(blank=True, default='', max_length=500)),
                        ('subtitle', models.CharField(blank=True, default='', help_text='Snapshot of sponsor (grant) or location (conference).', max_length=500)),
                        ('deadline_date', models.DateField(blank=True, help_text='The actionable date this save is tracking (snapshot).', null=True)),
                        ('deadline_kind', models.CharField(choices=[('application', 'Application'), ('abstract', 'Abstract'), ('manuscript', 'Manuscript'), ('event', 'Event'), ('other', 'Other')], default='other', max_length=20)),
                        ('snapshot', models.JSONField(blank=True, default=dict, help_text='Full display fields captured at save time (survives prune).')),
                        ('note', models.TextField(blank=True, default='')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('content', models.ForeignKey(blank=True, help_text='Global source item; nulled if the item is later pruned.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='saves', to='content.contentitem')),
                        ('target_lab', models.ForeignKey(blank=True, help_text='Set for a lab save; null for a personal save.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='saved_opportunities', to='accounts.lab')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='saved_opportunities', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'content_savedopportunity',
                        'ordering': ['deadline_date', 'created_at'],
                    },
                ),
                migrations.AddIndex(
                    model_name='announcement',
                    index=models.Index(fields=['state', 'category'], name='content_ann_state_542cc0_idx'),
                ),
                migrations.AddConstraint(
                    model_name='announcement',
                    constraint=models.CheckConstraint(condition=models.Q(models.Q(('target_lab__isnull', False), ('target_department__isnull', True)), models.Q(('target_department__isnull', False), ('target_lab__isnull', True)), _connector='OR'), name='announcement_one_target'),
                ),
                migrations.AddConstraint(
                    model_name='announcement',
                    constraint=models.UniqueConstraint(condition=models.Q(('content__isnull', False), ('target_lab__isnull', False)), fields=('target_lab', 'content'), name='announcement_unique_lab_item'),
                ),
                migrations.AddConstraint(
                    model_name='announcement',
                    constraint=models.UniqueConstraint(condition=models.Q(('content__isnull', False), ('target_department__isnull', False)), fields=('target_department', 'content'), name='announcement_unique_department_item'),
                ),
                migrations.AddConstraint(
                    model_name='announcementnudge',
                    constraint=models.UniqueConstraint(condition=models.Q(('user__isnull', False)), fields=('announcement', 'user', 'offset'), name='announcement_nudge_unique'),
                ),
                migrations.AddConstraint(
                    model_name='announcementnudge',
                    constraint=models.UniqueConstraint(condition=models.Q(('user__isnull', True)), fields=('announcement', 'discord_user_id', 'offset'), name='announcement_nudge_guest_unique'),
                ),
                migrations.AddConstraint(
                    model_name='announcementnudge',
                    constraint=models.CheckConstraint(condition=models.Q(('user__isnull', False), models.Q(('discord_user_id', ''), _negated=True), _connector='OR'), name='announcement_nudge_has_someone'),
                ),
                migrations.AddConstraint(
                    model_name='announcementpost',
                    constraint=models.UniqueConstraint(fields=('announcement', 'binding'), name='announcement_post_unique'),
                ),
                migrations.AddIndex(
                    model_name='announcementreaction',
                    index=models.Index(fields=['announcement', 'user', 'created_at'], name='content_ann_announc_57947a_idx'),
                ),
                migrations.AddConstraint(
                    model_name='announcementsettings',
                    constraint=models.CheckConstraint(condition=models.Q(models.Q(('target_lab__isnull', False), ('target_department__isnull', True)), models.Q(('target_department__isnull', False), ('target_lab__isnull', True)), _connector='OR'), name='announcement_settings_one_target'),
                ),
                migrations.AddConstraint(
                    model_name='closingsoonpost',
                    constraint=models.UniqueConstraint(fields=('binding', 'category', 'on_date'), name='closing_soon_post_unique_day'),
                ),
                migrations.AddIndex(
                    model_name='collection',
                    index=models.Index(fields=['project', 'is_archived'], name='content_col_project_6ea06a_idx'),
                ),
                migrations.AddConstraint(
                    model_name='collectionitem',
                    constraint=models.UniqueConstraint(fields=('collection', 'content'), name='content_collection_item_unique'),
                ),
                migrations.AddConstraint(
                    model_name='dailybriefing',
                    constraint=models.CheckConstraint(condition=models.Q(models.Q(('user__isnull', False), ('lab__isnull', True)), models.Q(('lab__isnull', False), ('user__isnull', True)), _connector='OR'), name='content_dailybriefing_exactly_one_target'),
                ),
                migrations.AddConstraint(
                    model_name='dailybriefing',
                    constraint=models.UniqueConstraint(condition=models.Q(('user__isnull', False)), fields=('user', 'generated_on', 'kind'), name='content_dailybriefing_user_day_kind_unique'),
                ),
                migrations.AddConstraint(
                    model_name='dailybriefing',
                    constraint=models.UniqueConstraint(condition=models.Q(('lab__isnull', False)), fields=('lab', 'generated_on', 'kind'), name='content_dailybriefing_lab_day_kind_unique'),
                ),
                migrations.AddIndex(
                    model_name='ignoreditem',
                    index=models.Index(fields=['user', 'content'], name='content_ign_user_id_57649c_idx'),
                ),
                migrations.AddConstraint(
                    model_name='ignoreditem',
                    constraint=models.UniqueConstraint(fields=('user', 'content'), name='content_ignored_item_unique_user_content'),
                ),
                migrations.AddIndex(
                    model_name='notification',
                    index=models.Index(fields=['user', 'dismissed_at', 'created_at'], name='content_not_user_id_da77aa_idx'),
                ),
                migrations.AddIndex(
                    model_name='projectalert',
                    index=models.Index(fields=['fired_on', 'status'], name='content_pro_fired_o_7c2400_idx'),
                ),
                migrations.AddConstraint(
                    model_name='projectalert',
                    constraint=models.CheckConstraint(condition=models.Q(models.Q(('target_user__isnull', False), ('target_lab__isnull', True)), models.Q(('target_lab__isnull', False), ('target_user__isnull', True)), _connector='OR'), name='content_projectalert_exactly_one_target'),
                ),
                migrations.AddConstraint(
                    model_name='projectalert',
                    constraint=models.UniqueConstraint(condition=models.Q(('target_user__isnull', False)), fields=('target_user', 'project', 'content', 'trigger'), name='content_projectalert_user_unique'),
                ),
                migrations.AddConstraint(
                    model_name='projectalert',
                    constraint=models.UniqueConstraint(condition=models.Q(('target_lab__isnull', False)), fields=('target_lab', 'project', 'content', 'trigger'), name='content_projectalert_lab_unique'),
                ),
                migrations.AddIndex(
                    model_name='projectitemseen',
                    index=models.Index(fields=['project', 'content'], name='content_pro_project_a169f7_idx'),
                ),
                migrations.AddConstraint(
                    model_name='projectitemseen',
                    constraint=models.UniqueConstraint(fields=('project', 'content'), name='content_project_item_seen_unique'),
                ),
                migrations.AddIndex(
                    model_name='projectshare',
                    index=models.Index(fields=['project', 'created_at'], name='content_pro_project_30214b_idx'),
                ),
                migrations.AddIndex(
                    model_name='membersuggestion',
                    index=models.Index(fields=['user', 'suggested', 'dismissed'], name='content_mem_user_id_80384f_idx'),
                ),
                migrations.AddConstraint(
                    model_name='membersuggestion',
                    constraint=models.UniqueConstraint(fields=('user', 'content'), name='content_member_suggestion_unique'),
                ),
                migrations.AddIndex(
                    model_name='reflectionproposal',
                    index=models.Index(fields=['status', 'expires_on'], name='content_ref_status_154401_idx'),
                ),
                migrations.AddConstraint(
                    model_name='reflectionproposal',
                    constraint=models.CheckConstraint(condition=models.Q(models.Q(('target_user__isnull', False), ('target_lab__isnull', True)), models.Q(('target_lab__isnull', False), ('target_user__isnull', True)), _connector='OR'), name='content_reflectionproposal_exactly_one_target'),
                ),
                migrations.AddIndex(
                    model_name='remindersubscription',
                    index=models.Index(fields=['state', 'due_date'], name='content_rem_state_183860_idx'),
                ),
                migrations.AddConstraint(
                    model_name='remindersubscription',
                    constraint=models.CheckConstraint(condition=models.Q(models.Q(('target_user__isnull', False), ('target_lab__isnull', True)), models.Q(('target_lab__isnull', False), ('target_user__isnull', True)), _connector='OR'), name='content_reminder_one_target'),
                ),
                migrations.AddConstraint(
                    model_name='remindersubscription',
                    constraint=models.UniqueConstraint(condition=models.Q(('content__isnull', False), ('target_user__isnull', False)), fields=('target_user', 'content', 'deadline_kind', 'deadline_round_key'), name='content_reminder_unique_user_content_round'),
                ),
                migrations.AddConstraint(
                    model_name='remindersubscription',
                    constraint=models.UniqueConstraint(condition=models.Q(('content__isnull', False), ('target_lab__isnull', False)), fields=('target_lab', 'content', 'deadline_kind', 'deadline_round_key'), name='content_reminder_unique_lab_content_round'),
                ),
                migrations.AddConstraint(
                    model_name='reminderoffset',
                    constraint=models.UniqueConstraint(fields=('subscription', 'amount', 'unit'), name='content_reminder_offset_unique'),
                ),
                migrations.AddConstraint(
                    model_name='remindermention',
                    constraint=models.UniqueConstraint(condition=models.Q(('member__isnull', False)), fields=('subscription', 'member'), name='content_reminder_mention_unique'),
                ),
                migrations.AddConstraint(
                    model_name='remindermention',
                    constraint=models.UniqueConstraint(condition=models.Q(('discord_id', ''), _negated=True), fields=('subscription', 'kind', 'discord_id'), name='content_reminder_mention_unique_discord'),
                ),
                migrations.AddConstraint(
                    model_name='remindermention',
                    constraint=models.UniqueConstraint(condition=models.Q(('kind', 'everyone')), fields=('subscription',), name='content_reminder_mention_single_everyone'),
                ),
                migrations.AddIndex(
                    model_name='reminderfire',
                    index=models.Index(fields=['subscription', 'fired_on'], name='content_rem_subscri_f92bba_idx'),
                ),
                migrations.AddIndex(
                    model_name='savedopportunity',
                    index=models.Index(fields=['user', 'deadline_date'], name='content_sav_user_id_959d03_idx'),
                ),
                migrations.AddIndex(
                    model_name='savedopportunity',
                    index=models.Index(fields=['target_lab', 'deadline_date'], name='content_sav_target__d4becd_idx'),
                ),
                migrations.AddConstraint(
                    model_name='savedopportunity',
                    constraint=models.UniqueConstraint(condition=models.Q(('content__isnull', False), ('target_lab__isnull', True)), fields=('user', 'content'), name='content_saved_opportunity_unique_user_content'),
                ),
                migrations.AddConstraint(
                    model_name='savedopportunity',
                    constraint=models.UniqueConstraint(condition=models.Q(('content__isnull', False), ('target_lab__isnull', False)), fields=('target_lab', 'content'), name='content_saved_opportunity_unique_lab_content'),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(move_content_types, restore_content_types),
    ]
