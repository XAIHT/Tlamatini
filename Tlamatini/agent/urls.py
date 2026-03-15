# agent/urls.py
from django.contrib.auth.decorators import login_required
from django.urls import path
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from . import views


def secure_get(view_func):
    return login_required(view_func)


def secure_post(view_func):
    protected_view = csrf_protect(require_POST(view_func))
    protected_view.csrf_exempt = False
    return login_required(protected_view)


urlpatterns = [
    path('', views.login_view, name='home'),
    path('agent/', secure_get(views.agent_page), name='agent_page'),
    path('welcome/', secure_get(views.welcome_view), name='welcome'),
    path('logout/', views.logout_view, name='logout'),
    path('load_canvas/<str:filename>/', secure_get(views.load_canvas_view), name='load_canvas'),
    path('load_prompt/<str:prompt_name>/', secure_get(views.load_prompt_view), name='load_prompt'),
    path('load_omissions/<str:omission_name>/', secure_get(views.load_omissions_view), name='load_omissions'),
    path('load_mcp/<str:mcp_name>/', secure_get(views.load_mcp_view), name='load_mcp'),
    path('load_tool/<str:tool_name>/', secure_get(views.load_tool_view), name='load_tool'),
    path('load_agent/<str:agent_name>/', secure_get(views.load_agent_view), name='load_agent'),
    path('load_agent_description/<str:agent_name>/', secure_get(views.load_agent_description_view), name='load_agent_description'),
    path('load_agent_config/<str:agent_name>/', secure_get(views.load_agent_config_view), name='load_agent_config'),
    path('agentic_control_panel/', secure_get(views.agentic_control_panel), name='agentic_control_panel'),
    path('save_agent_config/<str:agent_name>/', secure_post(views.save_agent_config_view), name='save_agent_config'),
    path('clear_pool/', secure_post(views.clear_pool_view), name='clear_pool'),
    path('cleanup_session/', secure_post(views.cleanup_session_view), name='cleanup_session'),
    path('clear_agent_logs/', secure_post(views.clear_all_agent_logs_view), name='clear_agent_logs'),
    path('delete_agent_pool_dir/<str:agent_name>/', secure_post(views.delete_agent_pool_dir_view), name='delete_agent_pool_dir'),
    path('deploy_agent_template/<str:agent_name>/', secure_post(views.deploy_agent_template_view), name='deploy_agent_template'),
    path('ensure_agent_exists/<str:agent_name>/', secure_post(views.ensure_agent_exists_view), name='ensure_agent_exists'),
    path('update_raiser_connection/<str:agent_name>/', secure_post(views.update_raiser_connection_view), name='update_raiser_connection'),
    path('update_emailer_connection/<str:agent_name>/', secure_post(views.update_emailer_connection_view), name='update_emailer_connection'),
    path('update_monitor_log_connection/<str:agent_name>/', secure_post(views.update_monitor_log_connection_view), name='update_monitor_log_connection'),
    path('update_ender_connection/<str:agent_name>/', secure_post(views.update_ender_connection_view), name='update_ender_connection'),
    path('update_starter_connection/<str:agent_name>/', secure_post(views.update_starter_connection_view), name='update_starter_connection'),
    path('update_whatsapper_connection/<str:agent_name>/', secure_post(views.update_whatsapper_connection_view), name='update_whatsapper_connection'),
    path('update_or_agent_connection/<str:agent_name>/', secure_post(views.update_or_agent_connection_view), name='update_or_agent_connection'),
    path('update_and_agent_connection/<str:agent_name>/', secure_post(views.update_and_agent_connection_view), name='update_and_agent_connection'),
    path('update_croner_connection/<str:agent_name>/', secure_post(views.update_croner_connection_view), name='update_croner_connection'),
    path('update_mover_connection/<str:agent_name>/', secure_post(views.update_mover_agent_connection), name='update_mover_agent_connection'),
    path('update_sleeper_connection/<str:agent_name>/', secure_post(views.update_sleeper_connection_view), name='update_sleeper_connection'),
    path('update_cleaner_connection/<str:agent_name>/', secure_post(views.update_cleaner_connection_view), name='update_cleaner_connection'),
    path('update_deleter_connection/<str:agent_name>/', secure_post(views.update_deleter_connection_view), name='update_deleter_connection'),
    path('update_notifier_connection/<str:agent_name>/', secure_post(views.update_notifier_connection_view), name='update_notifier_connection'),
    path('update_executer_connection/<str:agent_name>/', secure_post(views.update_executer_connection_view), name='update_executer_connection'),
    path('update_pythonxer_connection/<str:agent_name>/', secure_post(views.update_pythonxer_connection_view), name='update_pythonxer_connection'),
    path('update_stopper_connection/<str:agent_name>/', secure_post(views.update_stopper_connection_view), name='update_stopper_connection'),
    path('update_recmailer_connection/<str:agent_name>/', secure_post(views.update_recmailer_connection_view), name='update_recmailer_connection'),
    path('asker_choice/<str:agent_name>/', secure_post(views.asker_choice_view), name='asker_choice'),
    path('execute_starter_agent/<str:agent_name>/', secure_post(views.execute_starter_agent_view), name='execute_starter_agent'),
    path('check_starter_log/<str:agent_name>/', secure_get(views.check_starter_log_view), name='check_starter_log'),
    path('execute_ender_agent/<str:agent_name>/', secure_post(views.execute_ender_agent_view), name='execute_ender_agent'),
    path('check_ender_log/<str:agent_name>/', secure_get(views.check_ender_log_view), name='check_ender_log'),
    path('check_agents_running/<str:agent_name>/', secure_get(views.check_agents_running_view), name='check_agents_running'),
    path('session_state/', secure_get(views.load_session_state_view), name='load_session_state'),
    path('save_session_state/', secure_post(views.save_session_state_view), name='save_session_state'),
    path('clear_session_state/', secure_post(views.clear_session_state_view), name='clear_session_state'),
    path('check_all_agents_status/', secure_get(views.check_all_agents_status_view), name='check_all_agents_status'),
    path('read_agent_log/<str:agent_name>/', secure_get(views.read_agent_log_view), name='read_agent_log'),
    path('restart_agent/<str:agent_name>/', secure_post(views.restart_agent_view), name='restart_agent'),
    path('clear_pos_files/', secure_post(views.clear_pos_files_view), name='clear_pos_files'),
    path('get_session_running_processes/', secure_get(views.get_session_running_processes_view), name='get_session_running_processes'),
    path('kill_session_processes/', secure_post(views.kill_session_processes_view), name='kill_session_processes'),
    path('restart_agents/', secure_post(views.restart_agents_view), name='restart_agents'),
    path('update_asker_connection/<str:agent_name>/', secure_post(views.update_asker_connection_view), name='update_asker_connection'),
    path('update_forker_connection/<str:agent_name>/', secure_post(views.update_forker_connection_view), name='update_forker_connection'),
    path('update_counter_connection/<str:agent_name>/', secure_post(views.update_counter_connection_view), name='update_counter_connection'),
    path('update_shoter_connection/<str:agent_name>/', secure_post(views.update_shoter_connection_view), name='update_shoter_connection'),
    path('update_ssher_connection/<str:agent_name>/', secure_post(views.update_ssher_connection_view), name='update_ssher_connection'),
    path('update_scper_connection/<str:agent_name>/', secure_post(views.update_scper_connection_view), name='update_scper_connection'),
    path('update_telegramrx_connection/<str:agent_name>/', secure_post(views.update_telegramrx_connection_view), name='update_telegramrx_connection'),
    path('update_telegramer_connection/<str:agent_name>/', secure_post(views.update_telegramer_connection_view), name='update_telegramer_connection'),
    path('update_sqler_connection/<str:agent_name>/', secure_post(views.update_sqler_connection_view), name='update_sqler_connection'),
    path('update_prompter_connection/<str:agent_name>/', secure_post(views.update_prompter_connection_view), name='update_prompter_connection'),
    path('update_gitter_connection/<str:agent_name>/', secure_post(views.update_gitter_connection_view), name='update_gitter_connection'),
    path('update_dockerer_connection/<str:agent_name>/', secure_post(views.update_dockerer_connection_view), name='update_dockerer_connection'),
    path('update_pser_connection/<str:agent_name>/', secure_post(views.update_pser_connection_view), name='update_pser_connection'),
    path('execute_flowcreator/<str:agent_name>/', secure_post(views.execute_flowcreator_view), name='execute_flowcreator'),
    path('check_flowcreator_result/<str:agent_name>/', secure_get(views.check_flowcreator_result_view), name='check_flowcreator_result'),
    path('clean_pool_except/<str:agent_name>/', secure_post(views.clean_pool_except_view), name='clean_pool_except'),
    path('update_kuberneter_connection/<str:agent_name>/', secure_post(views.update_kuberneter_connection_view), name='update_kuberneter_connection'),
    path('update_apirer_connection/<str:agent_name>/', secure_post(views.update_apirer_connection_view), name='update_apirer_connection'),
    path('update_jenkinser_connection/<str:agent_name>/', secure_post(views.update_jenkinser_connection_view), name='update_jenkinser_connection'),
    path('update_crawler_connection/<str:agent_name>/', secure_post(views.update_crawler_connection_view), name='update_crawler_connection'),
    path('update_summarizer_connection/<str:agent_name>/', secure_post(views.update_summarizer_connection_view), name='update_summarizer_connection'),
    path('update_flowhypervisor_connection/<str:agent_name>/', secure_post(views.update_flowhypervisor_connection_view), name='update_flowhypervisor_connection'),
    path('update_mouser_connection/<str:agent_name>/', secure_post(views.update_mouser_connection_view), name='update_mouser_connection'),
    path('execute_flowhypervisor/<str:agent_name>/', secure_post(views.execute_flowhypervisor_view), name='execute_flowhypervisor'),
    path('check_flowhypervisor_alert/<str:agent_name>/', secure_get(views.check_flowhypervisor_alert_view), name='check_flowhypervisor_alert'),
    path('validate_flow/', secure_get(views.validate_flow_view), name='validate_flow'),
]

